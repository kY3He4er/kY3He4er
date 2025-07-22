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

    def add_project(self, name: str) -> bool:
        """Add a new project. Returns True if added, False if already exists."""
        with sqlite3.connect(self.path) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO projects(name) VALUES(?)", (name,))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

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


POMODORO_DURATION = 25 * 60
BREAK_DURATION = 5 * 60


class Timer(threading.Thread):
    def __init__(self, duration: int, on_finish=None, on_duration=None, allow_overrun=False):
        super().__init__(daemon=True)
        self.duration = duration
        self.on_finish = on_finish
        self.on_duration = on_duration
        self.allow_overrun = allow_overrun
        self.elapsed = 0
        self.paused = False
        self.running = False
        self._lock = threading.Lock()
        self._duration_called = False

    def run(self):
        self.running = True
        while self.running and (self.allow_overrun or self.elapsed < self.duration):
            time.sleep(1)
            with self._lock:
                if not self.paused:
                    self.elapsed += 1
                    remaining = self.duration - self.elapsed
                    if remaining >= 0:
                        msg = f"\rTime left: {remaining//60:02d}:{remaining%60:02d}"
                    else:
                        msg = f"\rOvertime: {(-remaining)//60:02d}:{(-remaining)%60:02d}"
                    print(msg, end="", flush=True)
                    if (
                        self.on_duration
                        and not self._duration_called
                        and self.elapsed >= self.duration
                    ):
                        self._duration_called = True
                        print()
                        self.on_duration()
        print()
        if self.elapsed >= self.duration and self.on_finish and not self.allow_overrun:
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
        self.awaiting_break = False
        self.break_timer = None

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

    def do_add(self, arg):
        """add <project> - add a new project"""
        project = arg.strip()
        if not project:
            project = input("Project name: ").strip()
        if not project:
            print("Project name required.")
            return
        added = self.db.add_project(project)
        if added:
            print(f"Project '{project}' added.")
        else:
            print(f"Project '{project}' already exists.")

    def _on_duration(self):
        print("Pomodoro finished. Press Enter to start break.")
        self.awaiting_break = True

    def _start_pomodoro(self, project: str) -> None:
        self.current_project_name = project
        self.current_project_id = self.db.create_or_get_project(project)
        self.session_start = int(time.time())
        self.timer = Timer(
            POMODORO_DURATION,
            on_duration=self._on_duration,
            allow_overrun=True,
        )
        self.timer.start()
        print(
            f"Started pomodoro for '{project}'. Type 'pause', 'resume', or 'stop' to control."
        )

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
        self._start_pomodoro(project)

    def _finish_session(self, reason: str = "finished") -> None:
        duration = self.timer.elapsed if self.timer else 0
        self.db.add_session(
            self.current_project_id,
            self.session_start,
            int(time.time()),
            duration,
        )
        print(
            f"Session for '{self.current_project_name}' {reason}. Duration {format_seconds(duration)}."
        )
        self.timer = None

    def _start_break(self) -> None:
        if not self.timer:
            return
        self.timer.stop()
        self.timer.join()
        self._finish_session()
        self.awaiting_break = False
        print(f"Starting break for {BREAK_DURATION // 60} minutes.")
        self.break_timer = Timer(BREAK_DURATION, on_finish=self._break_finished)
        self.break_timer.start()

    def _break_finished(self) -> None:
        self.break_timer = None
        print("Break finished. Starting next pomodoro.")
        if self.current_project_name:
            self._start_pomodoro(self.current_project_name)

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
        self._finish_session("stopped")

    def emptyline(self):
        if self.awaiting_break:
            self._start_break()
        else:
            pass

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
