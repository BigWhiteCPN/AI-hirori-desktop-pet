"""Built-in relationship and boundary lexicons.

The encoded literals are intentional: they keep sensitive examples out of plain
source view while preserving deterministic local matching behavior.
"""

import base64


def decode_builtin_lexicon(*encoded_items):
    return tuple(base64.b64decode(item).decode("utf-8") for item in encoded_items)


INTIMATE_BOUNDARY_BODY_TERMS = decode_builtin_lexicon(
    "6IO4",
    "5bGB6IKh",
    "6IeA",
    "6IW/",
    "6IWw",
    "6IKa5a2Q",
    "6Lqr5L2T",
    "6Lqr5LiK",
    "56eB5a+G",
    "6ISx",
    "6IiU",
    "552h5LiA6LW3",
    "5LiK5bqK",
)
INTIMATE_BOUNDARY_ACTION_TERMS = decode_builtin_lexicon("5pG4", "56Kw", "5Lqy", "5oqx", "6LS0", "6Lmt")
INTIMATE_BOUNDARY_SOFT_TERMS = decode_builtin_lexicon("5pG45aS0", "5ouN5ouN5aS0", "54m15omL", "5oqx5oqx", "5oul5oqx")
HARD_BOUNDARY_REPLY_TERMS = decode_builtin_lexicon(
    "5LiN5YeG5pG4",
    "6LaK5p2l6LaK6L+H5YiG",
    "6ZmN57qn5oiQ5pmu6YCa5pyL5Y+L",
    "5YaN6L+Z5qC3",
    "6K2m5ZGK5L2g",
    "5bqV57q/55qE5aW95ZCX",
)
AFFECTIONATE_PHRASE_TERMS = decode_builtin_lexicon(
    "5Zac5qyi5L2g",
    "54ix5L2g",
    "5oOz5L2g",
    "5Zyo5LmO5L2g",
    "6ZyA6KaB5L2g",
    "6Zmq552A5L2g",
    "6Zmq6Zmq5oiR",
    "5L2g55yf5aW9",
    "6LCi6LCi5L2g",
    "6L6b6Ium5LqG",
    "5pma5a6J",
    "5pep5a6J",
    "5a6d6LSd",
    "5Lqy54ix55qE",
    "5oqx5oqx",
    "5Lqy5Lqy",
    "6ICB5amG",
    "5aWz5pyL5Y+L",
)
RELATION_ESCALATION_TERMS = decode_builtin_lexicon("6ICB5amG", "5aWz5pyL5Y+L", "57uT5ama")
RELATION_PRESSURE_PENALTY_TERMS = RELATION_ESCALATION_TERMS + decode_builtin_lexicon("5Lqy5Lqy")

