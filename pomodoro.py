import argparse
import cmd
import datetime
import sqlite3
import threading
import time

DB_PATH = "pomodoro.db"


def format_seconds(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class DBManager:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._setup()

    def _setup(self) -> None:
        with sqlite3.connect(self.path) as conn:
            c = conn.cursor()
            c.execute(
                """CREATE TABLE IF NOT EXISTS projects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                active INTEGER DEFAULT 1
            )"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                start_time INTEGER,
                end_time INTEGER,
                duration INTEGER,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )"""
            )
            conn.commit()

    def create_or_get_project(self, name: str) -> int:
        with sqlite3.connect(self.path) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM projects WHERE name=?", (name,))
            row = c.fetchone()
            if row:
                return row[0]
            c.execute("INSERT INTO projects(name) VALUES(?)", (name,))
            conn.commit()
            return c.lastrowid

    def add_session(
        self, project_id: int, start_time: int, end_time: int, duration: int
    ) -> None:
        with sqlite3.connect(self.path) as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO sessions(project_id, start_time, end_time, duration)
                VALUES (?,?,?,?)""",
                (project_id, start_time, end_time, duration),
            )
            conn.commit()

    def get_active_projects(self):
        now = datetime.datetime.now()
        week_start = now.date() - datetime.timedelta(days=now.weekday())
        week_start_ts = int(
            datetime.datetime.combine(week_start, datetime.time()).timestamp()
        )
        week_end_ts = week_start_ts + 7 * 24 * 60 * 60
        with sqlite3.connect(self.path) as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM projects WHERE active=1 ORDER BY name")
            data = []
            for pid, name in c.fetchall():
                total = c.execute(
                    "SELECT COALESCE(SUM(duration),0) FROM sessions WHERE project_id=?",
                    (pid,),
                ).fetchone()[0]
                week = c.execute(
                    """SELECT COALESCE(SUM(duration),0) FROM sessions
                    WHERE project_id=? AND start_time>=? AND start_time<?""",
                    (pid, week_start_ts, week_end_ts),
                ).fetchone()[0]
                data.append((pid, name, total, week))
        return data


class Timer(threading.Thread):
    def __init__(self, duration: int, on_finish=None):
        super().__init__(daemon=True)
        self.duration = duration
        self.on_finish = on_finish
        self.elapsed = 0
        self.paused = False
        self.running = False
        self._lock = threading.Lock()

    def run(self):
        self.running = True
        while self.running and self.elapsed < self.duration:
            time.sleep(1)
            with self._lock:
                if not self.paused:
                    self.elapsed += 1
                    remaining = self.duration - self.elapsed
                    print(
                        f"\rTime left: {remaining//60:02d}:{remaining%60:02d}",
                        end="",
                        flush=True,
                    )
        print()
        if self.running and self.on_finish:
            self.on_finish()

    def pause(self):
        with self._lock:
            self.paused = True

    def resume(self):
        with self._lock:
            self.paused = False

    def stop(self):
        with self._lock:
            self.running = False


class PomodoroApp(cmd.Cmd):
    intro = "Pomodoro tracker. Type help or ? to list commands."
    prompt = "(pomodoro) "

    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.timer = None
        self.current_project_id = None
        self.current_project_name = None
        self.session_start = None

    # utility
    def _list_projects(self):
        projects = self.db.get_active_projects()
        if not projects:
            print("No active projects.")
            return
        print("Active projects:")
        for pid, name, total, week in projects:
            print(
                f"- {pid}. {name}: total {format_seconds(total)}, this week {format_seconds(week)}"
            )

    def preloop(self):
        self._list_projects()

    # commands
    def do_list(self, arg):
        """Show active projects and their times."""
        self._list_projects()

    def do_start(self, arg):
        """start <project> - start pomodoro for project"""
        if self.timer and self.timer.running:
            print("Session already running. Stop it first.")
            return
        project = arg.strip()
        if not project:
            project = input("Project name: ").strip()
        if not project:
            print("Project name required.")
            return
        self._list_projects()
        self.current_project_name = project
        self.current_project_id = self.db.create_or_get_project(project)
        self.session_start = int(time.time())
        self.timer = Timer(25 * 60, self._auto_finish)
        self.timer.start()
        print(
            f"Started pomodoro for '{project}'. Type 'pause', 'resume', or 'stop' to control."
        )

    def _auto_finish(self):
        duration = self.timer.elapsed
        self.db.add_session(
            self.current_project_id,
            self.session_start,
            int(time.time()),
            duration,
        )
        print(
            f"Session for '{self.current_project_name}' finished. Duration {format_seconds(duration)}."
        )
        self.timer = None

    def do_pause(self, arg):
        """Pause running pomodoro."""
        if not self.timer or not self.timer.running:
            print("No session running.")
            return
        self.timer.pause()
        print("Paused.")

    def do_resume(self, arg):
        """Resume paused pomodoro."""
        if not self.timer or not self.timer.running:
            print("No session running.")
            return
        self.timer.resume()
        print("Resumed.")

    def do_stop(self, arg):
        """Stop current pomodoro and record time."""
        if not self.timer:
            print("No session running.")
            return
        self.timer.stop()
        self.timer.join()
        duration = self.timer.elapsed
        self.db.add_session(
            self.current_project_id,
            self.session_start,
            int(time.time()),
            duration,
        )
        print(
            f"Session for '{self.current_project_name}' stopped. Duration {format_seconds(duration)}."
        )
        self.timer = None

    def do_exit(self, arg):
        """Exit application."""
        if self.timer and self.timer.running:
            print("Stop the running session before exiting.")
            return False
        return True

    def do_EOF(self, arg):  # noqa: N802
        print()
        return self.do_exit(arg)


if __name__ == "__main__":
    PomodoroApp().cmdloop()
