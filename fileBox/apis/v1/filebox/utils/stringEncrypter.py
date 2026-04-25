import os
from cryptography.fernet import Fernet

cipher_suite = Fernet(os.getenv('STRING_ENCRYPTER_KEY') or "")

#this function is used to encrypt the string, it takes a plain text as input and returns the encrypted text. If the plain text is empty or None, it returns None.
def encrypt_string(plain_text) -> str | None:
    if not plain_text:
        return None
    encrypted_text = cipher_suite.encrypt(plain_text.encode())  #we need to encode the plain text to bytes before encryption
    return encrypted_text.decode()

#this function is used to decrypt the string, it takes an encrypted text as input and returns the decrypted text. If the encrypted text is empty or None, it returns None.
def decrypt_string(plain_text) -> str | None:
    if not plain_text:
        return None
    decrypted_text = cipher_suite.decrypt(plain_text.encode())  #we need to encode the encrypted text to bytes before decryption
    return decrypted_text.decode()