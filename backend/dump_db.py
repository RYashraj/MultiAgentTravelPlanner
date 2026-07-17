import sqlite3

def dump_database():
    conn = sqlite3.connect("voyagerai.db")
    cursor = conn.cursor()
    
    print("=========================================")
    print("        SQLITE DATABASE DUMP")
    print("=========================================\n")
    
    # 1. Show Users
    print("--- [users] table ---")
    try:
        cursor.execute("SELECT id, email, full_name, created_at FROM users")
        users = cursor.fetchall()
        for u in users:
            print(f"ID: {u[0]} | Email: {u[1]} | Name: {u[2]} | Registered: {u[3]}")
    except Exception as e:
        print("Error reading users:", e)
        
    print("\n--- [trips] table ---")
    try:
        cursor.execute("SELECT id, user_id, destination, status, created_at FROM trips")
        trips = cursor.fetchall()
        for t in trips:
            print(f"Trip ID: {t[0]} | User ID: {t[1]} | Destination: {t[2]} | Status: {t[3]}")
    except Exception as e:
        print("Error reading trips:", e)
        
    print("\n--- [messages] table ---")
    try:
        cursor.execute("SELECT id, trip_id, role, content, created_at FROM messages")
        msgs = cursor.fetchall()
        for m in msgs:
            # truncate message content for display
            content_snippet = m[3][:50] + "..." if len(m[3]) > 50 else m[3]
            print(f"Msg ID: {m[0]} | Trip ID: {m[1]} | Role: {m[2]} | Content: {content_snippet}")
    except Exception as e:
        print("Error reading messages:", e)

    conn.close()

if __name__ == "__main__":
    dump_database()
