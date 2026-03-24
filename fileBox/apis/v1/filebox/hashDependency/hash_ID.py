from hashids import Hashids
from django.conf import settings

hashid = Hashids(salt=settings.SECRET_KEY, min_length=8)

def encode_id(id):
    if id is None:
        return None
    return hashid.encode(id)

def decode_id(id):
    if id is None:
        return None
    decoded = hashid.decode(id)
    return decoded[0] if decoded else None