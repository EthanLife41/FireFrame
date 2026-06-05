from datetime import datetime, timedelta

def get_placeholder_events() -> list:
    # Returns some placeholder events for v1 testing
    now = datetime.now()
    
    events = [
        {
            "id": "1",
            "title": "Team Standup",
            "start": (now + timedelta(minutes=15)).isoformat(),
            "end": (now + timedelta(minutes=45)).isoformat(),
            "location": "Zoom"
        },
        {
            "id": "2",
            "title": "Deep Work Block",
            "start": (now + timedelta(hours=2)).isoformat(),
            "end": (now + timedelta(hours=4)).isoformat(),
            "location": ""
        },
        {
            "id": "3",
            "title": "Review PRs",
            "start": (now + timedelta(hours=4, minutes=30)).isoformat(),
            "end": (now + timedelta(hours=5)).isoformat(),
            "location": "GitHub"
        }
    ]
    return events
