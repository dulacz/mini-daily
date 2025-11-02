#!/usr/bin/env python3
"""
Add missing activity completions for 2025-10-05
"""

import sqlite3
from datetime import datetime

def add_activities():
    # Connect to the database
    conn = sqlite3.connect('data/checkins.db')
    cursor = conn.cursor()
    
    # make up date
    acitivity_date = '2025-10-06'
    
    # Activities to add
    activities = [
        ('meaning', 'programming'),
        ('fitness', 'workout'),
        ('duty', 'understand'),
    ]
    
    try:
        # Check the table structure first
        cursor.execute("PRAGMA table_info(activity_completions)")
        columns = cursor.fetchall()
        print("Table structure:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        print()
        
        # Insert the completions
        for task, activity in activities:
            # Check if this activity already exists for this date
            cursor.execute('''
                SELECT id, completed FROM activity_completions 
                WHERE task = ? AND activity = ? AND date = ?
            ''', (task, activity, acitivity_date))
            existing = cursor.fetchone()
            
            if existing:
                print(f"Already exists: {task}-{activity} for {acitivity_date} (id={existing[0]}, completed={existing[1]})")
            else:
                cursor.execute('''
                    INSERT INTO activity_completions (task, activity, date, completed)
                    VALUES (?, ?, ?, 1)
                ''', (task, activity, acitivity_date))
                print(f"Added: {task}-{activity} for {acitivity_date}")
        
        # Commit the changes
        conn.commit()
        print(f"\n✅ Successfully added {len(activities)} activity completions for {acitivity_date}")
        
        # Verify the insertions
        cursor.execute('''
            SELECT task, activity, date, completed FROM activity_completions 
            WHERE date = ?
            ORDER BY task, activity
        ''', (acitivity_date,))
        results = cursor.fetchall()
        
        print(f"\nVerification - Records for {acitivity_date}:")
        for row in results:
            print(f"  {row[0]}-{row[1]}: completed={row[3]}")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
    finally:
        conn.close()

def upsert_activity(date, task, activity, completed, completed_at):
    conn = sqlite3.connect('data/checkins.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO activity_completions (date, task, activity, completed, completed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, task, activity) DO UPDATE SET
                completed=excluded.completed,
                completed_at=excluded.completed_at
        ''', (date, task, activity, completed, completed_at))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error during upsert: {e}")
        conn.rollback()
    finally:
        conn.close()
    print(f"\nUpserted: {task}-{activity} for {date} with completed={completed}")


if __name__ == "__main__":
    # add_activities()
    upsert_activity(
        date='2025-09-04',
        task='avoidance',
        activity='negative_thoughts',
        completed=1,
        completed_at=datetime(2025, 9, 4, 10, 0, 0).isoformat()
    )
