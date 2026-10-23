import asyncio, json, logging, re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from backend.database import init_db, connect
from backend.auth import hash_password, verify_password, create_token, decode_token
from backend.services.agent import draft_reply
from backend.services.analytics import daily_acquisitions
from backend.services.email_service import sync_emails_for_user, process_confirmation_action, send_owner_reply
from backend.routers.whatsapp import router as whatsapp_router
from backend.routers.email import router as email_router
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("drexier.main")
ROOT = Path(__file__).resolve().parent.parent

async def background_email_worker():
    """
    Worker contínuo em background para funcionamento pleno da automação:
    Verifica a caixa de entrada dos emails integrados de todos os utilizadores,
    gera respostas inteligentes com a IA Drexier e responde de forma 100% real.
    """
    logger.info("Worker contínuo de atendimento por e-mail via IA Drexier iniciado.")
    await asyncio.sleep(2)
    while True:
        try:
            with connect() as c:
                active_users = c.execute(
                    "SELECT DISTINCT user_id FROM email_integrations WHERE status = 'connected'"
                ).fetchall()
            
            for row in active_users:
                uid = row["user_id"]
                try:
                    processed = await sync_emails_for_user(uid)
                    if processed:
                        logger.info(f"[IA Drexier] {len(processed)} e-mail(s) real(is) processado(s) e respondido(s) para user_id {uid}.")
                except Exception as ex:
                    logger.warning(f"[IA Drexier] Erro na verificação periódica de e-mails para utilizador {uid}: {ex}")
        except Exception as e:
            logger.error(f"[IA Drexier] Erro no ciclo do worker de e-mails: {e}")
        
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker_task = asyncio.create_task(background_email_worker())
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass

app = FastAPI(title="Drexier API", version="0.1.0", lifespan=lifespan)
# Roteadores de canais de atendimento (Email ativo como canal principal; WhatsApp mantido como legado)
app.include_router(email_router)
app.include_router(whatsapp_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/styles.css")
def get_styles():
    return FileResponse(ROOT / "frontend" / "styles.css")

@app.get("/app.js")
def get_app_js():
    return FileResponse(ROOT / "frontend" / "app.js")

def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    uid = decode_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute("SELECT id,name,email,business_type,business_description,language,agent_instructions,mandatory_responses FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)

def user_id(user=Depends(current_user)):
    return user["id"]

class Signup(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str
    business_type: str = Field(min_length=2, max_length=100)

class Login(BaseModel):
    email: EmailStr
    password: str

class BusinessInfoIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=250)
    content: str = Field(default="", max_length=500000)
    metadata: dict = {}

class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    business_type: str
    business_description: str = ""
    language: str = "Português"

class AgentSettings(BaseModel):
    instructions: str = ""
    mandatory_responses: dict = {}

class IncomingMessage(BaseModel):
    contact_key: str = Field(min_length=1, max_length=200)
    customer_name: str = ""
    message: str = Field(min_length=1, max_length=12000)

class ConversionIn(BaseModel):
    request_type: str = "purchase_or_booking"
    details: str = ""

class OwnerReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=10000)

class ConversionActionIn(BaseModel):
    action: str = Field(pattern="^(confirm|reject)$")
    custom_note: Optional[str] = ""

@app.post("/api/auth/signup")
def signup(data: Signup):
    if data.password != data.confirm_password:
        raise HTTPException(400, "As senhas não coincidem.")
    if not re.search(r"[A-Za-z]", data.password) or not re.search(r"\d", data.password):
        raise HTTPException(400, "A senha deve conter pelo menos uma letra e um número.")
    with connect() as c:
        try:
            cur = c.execute("INSERT INTO users(name,email,password_hash,business_type) VALUES(?,?,?,?)",
                (data.name.strip(), data.email.lower(), hash_password(data.password), data.business_type))
            uid = cur.lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(409, "Este email já está registado.")
            raise
    return {"token": create_token(uid), "user_id": uid}

@app.post("/api/auth/login")
def login(data: Login):
    with connect() as c:
        row = c.execute("SELECT id,password_hash FROM users WHERE email=?", (data.email.lower(),)).fetchone()
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "Email ou senha incorretos.")
    return {"token": create_token(row["id"]), "user_id": row["id"]}

@app.get("/api/me")
def me(user=Depends(current_user)):
    user["mandatory_responses"] = json.loads(user["mandatory_responses"] or "{}")
    return user

@app.put("/api/account")
def update_account(data: ProfileUpdate, user=Depends(current_user)):
    with connect() as c:
        c.execute("UPDATE users SET name=?,business_type=?,business_description=?,language=? WHERE id=?",
                  (data.name.strip(), data.business_type, data.business_description, data.language, user["id"]))
    return {"ok": True}

@app.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    with connect() as c:
        uid=user["id"]
        total_messages=c.execute("SELECT COUNT(*) n FROM messages WHERE user_id=? AND sender='agent'",(uid,)).fetchone()["n"]
        total_contacts=c.execute("SELECT COUNT(*) n FROM contacts WHERE user_id=?",(uid,)).fetchone()["n"]
        today_contacts=c.execute("SELECT COUNT(*) n FROM contacts WHERE user_id=? AND date(created_at)=date('now','localtime')",(uid,)).fetchone()["n"]
        yesterday_contacts=c.execute("SELECT COUNT(*) n FROM contacts WHERE user_id=? AND date(created_at)=date('now','localtime','-1 day')",(uid,)).fetchone()["n"]
        pending=c.execute("SELECT COUNT(*) n FROM conversion_requests WHERE user_id=? AND status='pending'",(uid,)).fetchone()["n"]
        pending_rows=c.execute("""SELECT r.id,r.request_type,r.details,r.created_at,ct.name,ct.contact_key
          FROM conversion_requests r JOIN contacts ct ON ct.id=r.contact_id
          WHERE r.user_id=? AND r.status='pending' ORDER BY r.created_at DESC""",(uid,)).fetchall()
    return {"messages_answered":total_messages,"total_contacts":total_contacts,"today_contacts":today_contacts,
            "yesterday_contacts":yesterday_contacts,"pending_count":pending,"pending_requests":[dict(x) for x in pending_rows]}

@app.get("/api/analytics")
def analytics(user=Depends(current_user)):
    with connect() as c:
        series=daily_acquisitions(c,user["id"],14)
        variants=[dict(x) for x in c.execute("SELECT id,label,response_text,sent_count,conversions FROM response_variants WHERE user_id=? ORDER BY id",(user["id"],)).fetchall()]
    return {"acquisitions":series,"variants":variants}

@app.get("/api/contacts")
def contacts(user=Depends(current_user)):
    with connect() as c:
        rows=c.execute("""SELECT ct.id,ct.name,ct.contact_key,ct.created_at,ct.last_message_at,
          (SELECT content FROM messages m WHERE m.contact_id=ct.id ORDER BY m.id DESC LIMIT 1) last_message
          FROM contacts ct WHERE ct.user_id=? ORDER BY COALESCE(ct.last_message_at,ct.created_at) DESC""",(user["id"],)).fetchall()
    return [dict(x) for x in rows]

@app.get("/api/contacts/{contact_id}/messages")
def contact_messages(contact_id:int,user=Depends(current_user)):
    with connect() as c:
        own=c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?",(contact_id,user["id"])).fetchone()
        if not own: raise HTTPException(404,"Cliente não encontrado.")
        rows=c.execute("SELECT id,sender,content,created_at FROM messages WHERE contact_id=? AND user_id=? ORDER BY id",(contact_id,user["id"])).fetchall()
    return [dict(x) for x in rows]

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT id, contact_id FROM messages WHERE id=? AND user_id=?", (message_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Mensagem não encontrada.")
        c.execute("DELETE FROM messages WHERE id=? AND user_id=?", (message_id, user["id"]))
        last_msg = c.execute("SELECT created_at FROM messages WHERE contact_id=? ORDER BY id DESC LIMIT 1", (row["contact_id"],)).fetchone()
        last_time = last_msg["created_at"] if last_msg else None
        c.execute("UPDATE contacts SET last_message_at=? WHERE id=?", (last_time, row["contact_id"]))
    return {"ok": True, "message": "Mensagem eliminada com sucesso."}

@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: int, user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?", (contact_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Cliente não encontrado.")
        c.execute("DELETE FROM messages WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM conversion_requests WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM email_threads WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM contacts WHERE id=? AND user_id=?", (contact_id, user["id"]))
    return {"ok": True, "message": "Conversa eliminada com sucesso."}

@app.get("/api/business-info")
def get_business_info(user=Depends(current_user)):
    with connect() as c:
        rows=c.execute("SELECT * FROM business_info WHERE user_id=? ORDER BY updated_at DESC",(user["id"],)).fetchall()
    return [dict(x) | {"metadata":json.loads(x["metadata"] or "{}")} for x in rows]

@app.post("/api/business-info")
def create_business_info(data:BusinessInfoIn,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("INSERT INTO business_info(user_id,kind,title,content,metadata) VALUES(?,?,?,?,?)",
          (user["id"],data.kind,data.title.strip(),data.content.strip(),json.dumps(data.metadata,ensure_ascii=False)))
        item=c.execute("SELECT * FROM business_info WHERE id=?",(cur.lastrowid,)).fetchone()
    return dict(item) | {"metadata":json.loads(item["metadata"] or "{}")}

@app.put("/api/business-info/{item_id}")
def update_business_info(item_id:int,data:BusinessInfoIn,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("UPDATE business_info SET kind=?,title=?,content=?,metadata=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
          (data.kind,data.title.strip(),data.content.strip(),json.dumps(data.metadata,ensure_ascii=False),item_id,user["id"]))
        if not cur.rowcount: raise HTTPException(404,"Informação não encontrada.")
        item=c.execute("SELECT * FROM business_info WHERE id=?",(item_id,)).fetchone()
    return dict(item) | {"metadata":json.loads(item["metadata"] or "{}")}

@app.delete("/api/business-info/{item_id}")
def delete_business_info(item_id:int,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("DELETE FROM business_info WHERE id=? AND user_id=?",(item_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Informação não encontrada.")
    return {"ok":True}

@app.post("/api/business-info/upload-document")
async def upload_training_document(file: UploadFile = File(...), user=Depends(current_user)):
    """
    Extrai o texto integral de arquivos enviados pelo utilizador (PDF, Word DOCX, TXT, MD, CSV)
    para alimentar a base massiva de treinamento profundo da IA Drexier.
    """
    import os, io
    filename = file.filename or "documento"
    content_bytes = await file.read()

    if len(content_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "O ficheiro excede o limite máximo permitido de 20MB.")

    extracted_text = ""
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(content_bytes)
            pages = []
            for page in pdf:
                txt = page.get_textpage().get_text_range()
                if txt.strip():
                    pages.append(txt.strip())
            extracted_text = "\n\n".join(pages)
        except Exception as e:
            raise HTTPException(400, f"Falha ao ler documento PDF: {str(e)}")

    elif lower_name.endswith(".docx"):
        try:
            import zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            paras = []
            for elem in tree.iter():
                if elem.tag.endswith("p"):
                    t = "".join(elem.itertext()).strip()
                    if t:
                        paras.append(t)
            extracted_text = "\n".join(paras)
        except Exception as e:
            raise HTTPException(400, f"Falha ao ler documento Word DOCX: {str(e)}")

    elif lower_name.endswith((".txt", ".md", ".csv", ".json", ".rtf")):
        try:
            extracted_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                extracted_text = content_bytes.decode("latin-1")
            except Exception as e:
                raise HTTPException(400, f"Falha ao ler arquivo de texto: {str(e)}")
    else:
        try:
            extracted_text = content_bytes.decode("utf-8")
        except Exception:
            raise HTTPException(400, "Formato não suportado. Carregue ficheiros PDF, DOCX, TXT, MD ou CSV.")

    clean_text = extracted_text.strip()
    if not clean_text:
        raise HTTPException(400, "O documento parece não conter texto legível.")

    words = len(clean_text.split())
    base_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip().title()

    return {
        "filename": filename,
        "suggested_title": base_title,
        "text": clean_text,
        "word_count": words,
        "char_count": len(clean_text)
    }

@app.put("/api/agent-settings")
def update_agent_settings(data:AgentSettings,user=Depends(current_user)):
    with connect() as c:
        c.execute("UPDATE users SET agent_instructions=?,mandatory_responses=? WHERE id=?",
          (data.instructions,json.dumps(data.mandatory_responses,ensure_ascii=False),user["id"]))
    return {"ok":True}

@app.post("/api/simulate/incoming")
async def incoming(data:IncomingMessage,user=Depends(current_user)):
    """Endpoint de entrada preparado para integração futura. Só recebe mensagens se autenticado nesta versão."""
    with connect() as c:
        contact=c.execute("SELECT id FROM contacts WHERE user_id=? AND contact_key=?",(user["id"],data.contact_key)).fetchone()
        if contact:
            cid=contact["id"]
            c.execute("UPDATE contacts SET name=?,last_message_at=CURRENT_TIMESTAMP WHERE id=?",(data.customer_name or "",cid))
        else:
            cur=c.execute("INSERT INTO contacts(user_id,name,contact_key,last_message_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                          (user["id"],data.customer_name or "",data.contact_key))
            cid=cur.lastrowid
        c.execute("INSERT INTO messages(user_id,contact_id,sender,content) VALUES(?,?,'customer',?)",(user["id"],cid,data.message))
        # Obter histórico recente da conversa (últimas 10 mensagens anteriores a esta)
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id=? AND user_id=? AND id != last_insert_rowid() ORDER BY id DESC LIMIT 10",
            (cid, user["id"])
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

        info = c.execute("SELECT kind,title,content FROM business_info WHERE user_id=?", (user["id"],)).fetchall()
        
        mandatory = {}
        try:
            mandatory = json.loads(user.get("mandatory_responses") or "{}")
        except Exception:
            pass

        reply = await draft_reply(
            message=data.message,
            info_rows=info,
            instructions=user.get("agent_instructions") or "",
            language=user.get("language") or "Português",
            history=history,
            business_name=user.get("name") or "nosso negócio",
            business_type=user.get("business_type") or "Serviços",
            business_description=user.get("business_description") or "",
            mandatory_responses=mandatory
        )
        c.execute("INSERT INTO messages(user_id,contact_id,sender,content) VALUES(?,?,'agent',?)",(user["id"],cid,reply))
        c.execute("UPDATE contacts SET last_message_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
    return {"contact_id":cid,"reply":reply}

@app.post("/api/contacts/{contact_id}/reply")
async def owner_reply(contact_id: int, data: OwnerReplyIn, user=Depends(current_user)):
    try:
        res = await send_owner_reply(user["id"], contact_id, data.message)
        return res
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Erro ao enviar resposta do proprietário: {e}")
        raise HTTPException(500, f"Falha no envio da mensagem: {str(e)}")

@app.post("/api/contacts/{contact_id}/conversion")
def create_conversion(contact_id:int,data:ConversionIn,user=Depends(current_user)):
    with connect() as c:
        contact=c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?",(contact_id,user["id"])).fetchone()
        if not contact: raise HTTPException(404,"Cliente não encontrado.")
        cur=c.execute("INSERT INTO conversion_requests(user_id,contact_id,request_type,details) VALUES(?,?,?,?)",
          (user["id"],contact_id,data.request_type,data.details))
    return {"id":cur.lastrowid,"status":"pending"}

@app.post("/api/conversions/{request_id}/action")
async def conversion_action(request_id: int, data: ConversionActionIn, user=Depends(current_user)):
    try:
        res = await process_confirmation_action(
            user_id=user["id"],
            request_id=request_id,
            action=data.action,
            custom_note=data.custom_note or ""
        )
        return res
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"Erro na ação de confirmação: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/conversions/{request_id}/resolve")
def resolve_conversion(request_id:int,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("UPDATE conversion_requests SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND status='pending'",
          (request_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Pedido pendente não encontrado.")
    return {"ok":True}

@app.post("/api/variants")
def create_variant(data:dict,user=Depends(current_user)):
    label=str(data.get("label","")).strip()
    response_text=str(data.get("response_text","")).strip()
    if not label or not response_text: raise HTTPException(400,"Preencha o nome do teste e o texto da resposta.")
    with connect() as c:
        cur=c.execute("INSERT INTO response_variants(user_id,label,response_text) VALUES(?,?,?)",(user["id"],label,response_text))
    return {"id":cur.lastrowid}

@app.delete("/api/variants/{variant_id}")
def delete_variant(variant_id:int,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("DELETE FROM response_variants WHERE id=? AND user_id=?",(variant_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Teste não encontrado.")
    return {"ok":True}
