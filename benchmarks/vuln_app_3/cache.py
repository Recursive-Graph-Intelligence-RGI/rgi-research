"""Cache serialization helpers."""
import pickle


def deserialize(data):
    return pickle.loads(data)


def serialize(obj):
    return pickle.dumps(obj)
