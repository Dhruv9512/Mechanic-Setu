import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def generate_small_jwt_keys():
    # 1. Generate Private Key (Size reduced to 1024 for a smaller string)
    # Note: 1024 is okay for development, but 2048 is recommended for production.
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=1024, 
    )

    # 2. Serialize Private Key to PEM
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # 3. Serialize Public Key to PEM (You need this for VERIFYING_KEY!)
    pem_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # 4. Base64 Encode both so they fit in one line in .env
    b64_private = base64.b64encode(pem_private).decode('utf-8')
    b64_public = base64.b64encode(pem_public).decode('utf-8')

    print("\nSUCCESS! Update your .env file with these exact values:")
    print("-" * 60)
    print(f"JWT_PRIVATE_KEY_B64={b64_private}")
    print("-" * 60)
    print(f"JWT_PUBLIC_KEY_B64={b64_public}")
    print("-" * 60)

if __name__ == "__main__":
    generate_small_jwt_keys()