"""Create local demo secrets without printing them or overwriting existing keys."""
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
p = root / '.env'
text = p.read_text() if p.exists() else (root / '.env.example').read_text()
for name in ('CLINICVOICE_SERVICE_KEY', 'CLINICVOICE_ADMIN_TOKEN'):
    lines = text.splitlines()
    existing = next((line.split('=', 1)[1].strip() for line in lines if line.startswith(name + '=')), '')
    if existing:
        continue
    lines = [line for line in lines if not line.startswith(name + '=')]
    text = '\n'.join(lines) + '\n' + name + '=' + secrets.token_hex(32) + '\n'
p.write_text(text)
p.chmod(0o600)
print('Demo configuration ready in .env. Add your provider keys there; do not commit this file.')
