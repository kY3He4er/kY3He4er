- 👋 Hi, I’m @kY3He4er
- 👀 I’m interested in collaborations, machine learning, big data
- 🌱 I’m currently learning python, SQL
- 💞️ I’m looking to collaborate on anything that could help me to improve
- 📫 How to reach me: DM, i'm online
- ⚡ Fun fact: ...

<!---
kY3He4er/kY3He4er is a ✨ special ✨ repository because its `README.md` (this file) appears on your GitHub profile.
You can click the Preview link to take a look at your changes.
--->

## Pomodoro Time Tracker

This repository includes a simple command line application for tracking time spent on projects using the Pomodoro technique. The script stores sessions in an SQLite database and allows you to pause or stop the timer.

### Usage

Run the application with Python:

```bash
python3 pomodoro.py
```

Available commands inside the app:

- `list` – show active projects with total and weekly time.
- `add <project>` – create a new project entry.
- `start <project>` – start a 25 minute Pomodoro for the specified project.
- `pause` – pause the running timer.
- `resume` – resume a paused timer.
- `stop` – stop the timer and record the session.
- `exit` – quit the application.

The data is stored in `pomodoro.db` in the repository directory.

