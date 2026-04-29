from app.services.rag_service import hybrid_search
from app.core.config import settings

hits = hybrid_search('Cisco security', settings.COLLECTION_VENDOR)
print(f'HITS: {len(hits)}')
for h in hits: print(h)
