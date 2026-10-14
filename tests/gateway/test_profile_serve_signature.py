"""#111105: the profile re-scan watcher must rebuild adapters after a config.yaml replacement
that keeps mtime and size (``cp -p``, ``rsync -t``, a timestamp-pinning writer)."""
import os
import shutil

from gateway.run_profile_reconcile import profile_serve_signature
from tests.waiting import wait_until


def _wait_for_ctime_tick(directory, after_ns):
    """Block until the filesystem timestamp clock has moved past ``after_ns``.

    Kernels without multigrain timestamps stamp inodes from a coarse, tick-granular clock, so an
    in-place rewrite within the same tick as the original write keeps ctime too — no stat-based
    signature can see it, and the replacement in production never lands in the same tick.
    """
    probe = directory / "ctime-probe"

    def _ticked():
        probe.touch()
        return probe.stat().st_ctime_ns > after_ns

    wait_until(_ticked, what="filesystem ctime clock to advance")


def test_profile_serve_signature_changes_on_replacement_with_pinned_mtime(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("x" * 64, encoding="utf-8")
    before = profile_serve_signature(tmp_path)
    assert profile_serve_signature(tmp_path) == before  # unchanged file: stable
    st = cfg.stat()
    _wait_for_ctime_tick(tmp_path, st.st_ctime_ns)
    other = tmp_path / "other"
    other.write_text("y" * 64, encoding="utf-8")
    shutil.copy2(other, cfg)
    os.utime(cfg, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert (cfg.stat().st_mtime_ns, cfg.stat().st_size) == (st.st_mtime_ns, st.st_size)
    assert profile_serve_signature(tmp_path) != before
