import gzip
import json

import pytest


@pytest.fixture
def tgs_file(tmp_path):
    # An original one-second animation: a red circle moves horizontally.
    data = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 30,
        "w": 128,
        "h": 128,
        "layers": [
            {
                "ty": 4,
                "ind": 1,
                "ip": 0,
                "op": 30,
                "st": 0,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {
                                "t": 0,
                                "s": [32, 64, 0],
                                "e": [96, 64, 0],
                                "o": {"x": [0.33], "y": [0.33]},
                                "i": {"x": [0.67], "y": [0.67]},
                            },
                            {"t": 29, "s": [96, 64, 0]},
                        ],
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "shapes": [
                    {"ty": "el", "p": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [32, 32]}},
                    {"ty": "fl", "c": {"a": 0, "k": [1, 0, 0, 1]}, "o": {"a": 0, "k": 100}},
                ],
            }
        ],
    }
    source = tmp_path / "moving-circle.tgs"
    source.write_bytes(gzip.compress(json.dumps(data).encode()))
    return source
