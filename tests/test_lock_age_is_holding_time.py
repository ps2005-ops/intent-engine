"""A reused lock file must not make a fresh cycle look stale."""
import os, time
from intent_engine.market import cycle as C
from intent_engine.runtime.locks import JobLock


def test_a_fresh_lock_on_an_old_file_is_not_stale(tmp_path):
    lock = tmp_path / "locks" / f"{C.LOCK_NAME}.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    old = time.time() - 120 * 86400
    os.utime(lock, (old, old))                       # created in August
    with JobLock(C.LOCK_NAME, root=tmp_path):
        st = C.lock_state(tmp_path)
    assert st["held"] is True
    assert st["age_seconds"] < 60 and st["stale"] is False
