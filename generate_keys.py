import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def get_small_key():
    # 1. Generate the Pair (Required to get the public key)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 2. Extract Public Key ("The Small Key")
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # 3. Serialize Private Key (Don't lose this!)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # 4. Convert to Base64 (for .env files)
    b64_public = base64.b64encode(pem_public).decode('utf-8')
    b64_private = base64.b64encode(pem_private).decode('utf-8')

    print("\n" + "="*60)
    print(" >>> HERE IS THE SMALL KEY (Public Key) <<<")
    print("="*60)
    print(f"JWT_PUBLIC_KEY_B64={b64_public}")
    print("="*60 + "\n")
    
    print("Make sure to also save the Private Key (Big Key),")
    print("or the small key above will be useless:")
    print("-" * 60)
    print(f"JWT_PRIVATE_KEY_B64={b64_private}")
    print("-" * 60 + "\n")

if __name__ == "__main__":
    get_small_key()