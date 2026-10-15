from datetime import date, timedelta

def daily_acquisitions(conn, user_id, days=14):
    result = []
    today = date.today()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        count = conn.execute(
            "SELECT COUNT(*) n FROM contacts WHERE user_id=? AND date(created_at)=?",
            (user_id, day.isoformat())
        ).fetchone()["n"]
        result.append({"date": day.isoformat(), "count": count})
    return result
