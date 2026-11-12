"""Entry point loaded by the organizer's Python 3.11 harness."""
from contract import Answer, Conflict, Source

from knowledge.evidence import History
from knowledge.query import answer_member
from knowledge.resolve import discover_conflicts


def _source(evidence):
    return Source(url=evidence.url, snapshot_id=evidence.snapshot_id, quote=evidence.quote)


class SnapshotKnowledge:
    def __init__(self):
        self._history = History()

    def ingest(self, snapshot):
        self._history.add(snapshot)

    def answer(self, question, as_of=None):
        reply = answer_member(self._history, question, as_of)
        return Answer(text=reply.text, sources=[_source(e) for e in reply.sources],
                      confident=reply.confident, conflict_note=reply.conflict_note)

    def conflicts(self):
        return [
            Conflict(topic=item.topic, values=list(item.values),
                     sources=[_source(e) for e in item.sources],
                     resolution=item.resolution, reason=item.reason)
            for item in discover_conflicts(self._history)
        ]


def build():
    return SnapshotKnowledge()
