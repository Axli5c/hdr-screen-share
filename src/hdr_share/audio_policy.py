"""Select disjoint audio process trees; ambiguous graphs are never captured."""
from dataclasses import dataclass
from pathlib import PureWindowsPath


class AudioPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    parent_pid: int
    created_at: int
    image_name: str


DISCORD_IMAGES = frozenset({'discord.exe', 'discordptb.exe', 'discordcanary.exe',
                            'discorddevelopment.exe'})


def select_capture_roots(processes: list[ProcessIdentity], audio_pids: set[int],
                         own_pid: int) -> list[ProcessIdentity]:
    table = {}
    for process in processes:
        if process.pid in table or process.created_at <= 0 or not process.image_name:
            raise AudioPolicyError('Ambiguous process identity')
        table[process.pid] = process
    if own_pid not in table:
        raise AudioPolicyError('Missing own process identity')
    if audio_pids - table.keys():
        raise AudioPolicyError('Unknown active audio process')

    def ancestors(pid):
        seen = {pid}
        current = table[pid]
        while parent := table.get(current.parent_pid):
            if parent.created_at > current.created_at:
                break  # Parent PID was reused after this child was created.
            if parent.pid in seen:
                raise AudioPolicyError('Process ancestry cycle')
            seen.add(parent.pid)
            yield parent.pid
            current = parent

    chains = {pid: set(ancestors(pid)) for pid in table}
    forbidden = {own_pid} | {p.pid for p in processes if
        PureWindowsPath(p.image_name).name.casefold() in DISCORD_IMAGES}
    excluded = forbidden | {pid for pid, chain in chains.items() if chain & forbidden}
    allowed = audio_pids - excluded
    for pid in allowed:
        if any(pid in chains[child] for child in excluded):
            raise AudioPolicyError('Capture tree contains an excluded process')
    return [table[pid] for pid in sorted(allowed) if not chains[pid] & allowed]
