import sqlite3
from typing import Optional
from bot.config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER UNIQUE NOT NULL,
            username        TEXT,
            first_name      TEXT,
            last_name       TEXT,
            x_username      TEXT,
            points          INTEGER NOT NULL DEFAULT 0,
            registered_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER NOT NULL,
            description     TEXT    NOT NULL,
            points_earned   INTEGER NOT NULL DEFAULT 5,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS raids (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_url         TEXT    NOT NULL,
            tweet_id          TEXT    NOT NULL,
            account_username  TEXT    NOT NULL,
            followers_count   TEXT    NOT NULL,
            tweet_content     TEXT    NOT NULL,
            added_by          INTEGER NOT NULL,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            is_active         INTEGER NOT NULL DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS raid_completions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            raid_id       INTEGER NOT NULL,
            telegram_id   INTEGER NOT NULL,
            reply_url     TEXT    NOT NULL,
            points_earned INTEGER NOT NULL DEFAULT 20,
            completed_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (raid_id)     REFERENCES raids (id),
            FOREIGN KEY (telegram_id) REFERENCES users (telegram_id),
            UNIQUE (raid_id, telegram_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS monitored_accounts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            username         TEXT    NOT NULL UNIQUE,
            twitter_user_id  TEXT,
            followers_count  TEXT    NOT NULL,
            added_by         INTEGER NOT NULL,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            is_active        INTEGER NOT NULL DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen_tweets (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id         TEXT    NOT NULL,
            tweet_content    TEXT    NOT NULL,
            tweet_url        TEXT    NOT NULL,
            account_username TEXT    NOT NULL,
            followers_count  TEXT    NOT NULL,
            telegram_id      INTEGER NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'seen',
            reply_url        TEXT,
            seen_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            completed_at     TEXT,
            UNIQUE (tweet_id, telegram_id)
        )
    """)
    # Migration: add last_raid_id column if missing
    try:
        c.execute("ALTER TABLE users ADD COLUMN last_raid_id INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Monitored accounts
# ---------------------------------------------------------------------------

def add_monitored_account(username: str, followers_count: str, added_by: int) -> bool:
    """Add an account to monitor. Returns False if already exists."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO monitored_accounts (username, followers_count, added_by) VALUES (?, ?, ?)",
            (username.lstrip("@"), followers_count, added_by),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_monitored_accounts() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM monitored_accounts WHERE is_active = 1"
    ).fetchall()
    conn.close()
    return rows


def update_twitter_user_id(username: str, twitter_user_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE monitored_accounts SET twitter_user_id = ? WHERE username = ?",
        (twitter_user_id, username),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Seen tweets
# ---------------------------------------------------------------------------

def is_tweet_seen(tweet_id: str, telegram_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM seen_tweets WHERE tweet_id = ? AND telegram_id = ?",
        (tweet_id, telegram_id),
    ).fetchone()
    conn.close()
    return row is not None


def mark_tweet_seen(
    tweet_id: str,
    tweet_content: str,
    tweet_url: str,
    account_username: str,
    followers_count: str,
    telegram_id: int,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO seen_tweets
               (tweet_id, tweet_content, tweet_url, account_username, followers_count, telegram_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tweet_id, tweet_content, tweet_url, account_username, followers_count, telegram_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_tweet(telegram_id: int) -> Optional[sqlite3.Row]:
    """Return the most recent seen-but-not-completed tweet for this user."""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM seen_tweets
           WHERE telegram_id = ? AND status = 'seen'
           ORDER BY seen_at DESC LIMIT 1""",
        (telegram_id,),
    ).fetchone()
    conn.close()
    return row


def complete_tweet(tweet_id: str, telegram_id: int, reply_url: str, points: int) -> bool:
    """Mark a tweet raid as completed and award points."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE seen_tweets SET status = 'completed', reply_url = ?,
               completed_at = datetime('now')
               WHERE tweet_id = ? AND telegram_id = ? AND status = 'seen'""",
            (reply_url, tweet_id, telegram_id),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "UPDATE users SET points = points + ? WHERE telegram_id = ?",
            (points, telegram_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_user(telegram_id: int) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.close()
    return row


def register_user(
    telegram_id: int,
    username: Optional[str],
    first_name: str,
    last_name: Optional[str],
    bonus_points: int,
) -> bool:
    """Insert a new user. Returns True on success, False if already registered."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO users (telegram_id, username, first_name, last_name, points)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, username, first_name, last_name, bonus_points),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def link_x_username(telegram_id: int, x_username: str, bonus_points: int) -> bool:
    """Set X username and award bonus points. Returns False if user not registered."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE users SET x_username = ?, points = points + ? WHERE telegram_id = ?",
        (x_username, bonus_points, telegram_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def log_task(telegram_id: int, description: str, points: int) -> bool:
    """Record a task and award points. Returns False if user not registered."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tasks (telegram_id, description, points_earned) VALUES (?, ?, ?)",
            (telegram_id, description, points),
        )
        conn.execute(
            "UPDATE users SET points = points + ? WHERE telegram_id = ?",
            (points, telegram_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_user_tasks(telegram_id: int, limit: int = 5) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT description, points_earned, created_at
           FROM tasks WHERE telegram_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (telegram_id, limit),
    ).fetchall()
    conn.close()
    return rows


def add_raid(
    tweet_url: str,
    tweet_id: str,
    account_username: str,
    followers_count: str,
    tweet_content: str,
    added_by: int,
) -> int:
    """Insert a new raid. Returns the new raid id."""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO raids (tweet_url, tweet_id, account_username, followers_count, tweet_content, added_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tweet_url, tweet_id, account_username, followers_count, tweet_content, added_by),
    )
    raid_id = cur.lastrowid
    conn.commit()
    conn.close()
    return raid_id


def get_available_raid(telegram_id: int) -> Optional[sqlite3.Row]:
    """Cycle through active uncompleted raids using a per-user cursor."""
    conn = get_conn()
    user = conn.execute(
        "SELECT last_raid_id FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    last_id = user["last_raid_id"] if user and user["last_raid_id"] else 0

    # Try the next raid AFTER the cursor
    row = conn.execute(
        """SELECT r.* FROM raids r
           WHERE r.is_active = 1
             AND r.id > ?
             AND r.id NOT IN (
                 SELECT rc.raid_id FROM raid_completions rc WHERE rc.telegram_id = ?
             )
           ORDER BY r.id ASC LIMIT 1""",
        (last_id, telegram_id),
    ).fetchone()

    # Wrap around: start from the beginning if nothing found after cursor
    if not row:
        row = conn.execute(
            """SELECT r.* FROM raids r
               WHERE r.is_active = 1
                 AND r.id NOT IN (
                     SELECT rc.raid_id FROM raid_completions rc WHERE rc.telegram_id = ?
                 )
               ORDER BY r.id ASC LIMIT 1""",
            (telegram_id,),
        ).fetchone()

    conn.close()
    return row


def set_last_raid_id(telegram_id: int, raid_id: int) -> None:
    """Update the user's raid cursor so the next /find shows a different raid."""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET last_raid_id = ? WHERE telegram_id = ?",
        (raid_id, telegram_id),
    )
    conn.commit()
    conn.close()


def get_latest_raid() -> Optional[sqlite3.Row]:
    """Return the most recent active raid regardless of user."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM raids WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def complete_raid(raid_id: int, telegram_id: int, reply_url: str, points: int) -> bool:
    """Record a raid completion and award points. Returns False if already done."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO raid_completions (raid_id, telegram_id, reply_url, points_earned)
               VALUES (?, ?, ?, ?)""",
            (raid_id, telegram_id, reply_url, points),
        )
        conn.execute(
            "UPDATE users SET points = points + ? WHERE telegram_id = ?",
            (points, telegram_id),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_recent_posts(limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT t.description, t.points_earned, t.created_at,
                  u.first_name, u.username
           FROM tasks t
           JOIN users u ON u.telegram_id = t.telegram_id
           ORDER BY t.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def get_leaderboard(limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT first_name, username, x_username, points
           FROM users ORDER BY points DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows
