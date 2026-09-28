import math
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func, desc, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Organization, User, Document, DocumentChunk, QueryLog, TelegramSession


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, org_id: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, name: str, org_id: Optional[str] = None) -> Organization:
        org = Organization(name=name)
        if org_id:
            org.id = org_id
        self.session.add(org)
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def list_all(self) -> List[Organization]:
        stmt = select(Organization).order_by(Organization.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_with_counts(self) -> List[Dict[str, Any]]:
        orgs = await self.list_all()
        results = []
        for org in orgs:
            user_count = await self.session.scalar(
                select(func.count(User.id)).where(User.organization_id == org.id)
            )
            doc_count = await self.session.scalar(
                select(func.count(Document.id)).where(Document.organization_id == org.id)
            )
            results.append({
                "id": org.id,
                "name": org.name,
                "created_at": org.created_at,
                "user_count": user_count or 0,
                "document_count": doc_count or 0
            })
        return results


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_employee_id(self, org_id: str, employee_id: str) -> Optional[User]:
        stmt = select(User).where(
            User.organization_id == org_id,
            User.employee_id == employee_id,
            User.status == "active"
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_employee_id(self, employee_id: str) -> List[User]:
        """Search by employee_id across active organizations."""
        stmt = select(User).where(
            User.employee_id == employee_id,
            User.status == "active"
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_email(self, email: str, org_id: Optional[str] = None) -> Optional[User]:
        stmt = select(User).where(User.email == email.strip().lower(), User.status == "active")
        if org_id:
            stmt = stmt.where(User.organization_id == org_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        organization_id: str,
        employee_id: str,
        name: str,
        email: str,
        role: str = "employee",
        status: str = "active",
        user_id: Optional[str] = None
    ) -> User:
        user = User(
            organization_id=organization_id,
            employee_id=employee_id,
            name=name,
            email=email.strip().lower(),
            role=role,
            status=status
        )
        if user_id:
            user.id = user_id
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_by_org(self, org_id: str) -> List[User]:
        stmt = select(User).where(User.organization_id == org_id).order_by(User.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        organization_id: str,
        filename: str,
        storage_path: str,
        file_size: int = 0,
        chunk_count: int = 0
    ) -> Document:
        doc = Document(
            organization_id=organization_id,
            filename=filename,
            storage_path=storage_path,
            file_size=file_size,
            chunk_count=chunk_count
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def get_by_id(self, doc_id: str, organization_id: str) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == doc_id,
            Document.organization_id == organization_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(self, organization_id: str) -> List[Document]:
        stmt = select(Document).where(
            Document.organization_id == organization_id
        ).order_by(desc(Document.uploaded_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, doc_id: str, organization_id: str) -> bool:
        stmt = delete(Document).where(
            Document.id == doc_id,
            Document.organization_id == organization_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chunks(self, chunks_data: List[Dict[str, Any]]) -> List[DocumentChunk]:
        chunks = []
        for data in chunks_data:
            chunk = DocumentChunk(
                document_id=data["document_id"],
                organization_id=data["organization_id"],
                content=data["content"],
                embedding=data.get("embedding"),
                chunk_metadata=data.get("chunk_metadata", {})
            )
            chunks.append(chunk)
            self.session.add(chunk)
        await self.session.commit()
        return chunks

    async def vector_search(
        self,
        organization_id: str,
        query_embedding: List[float],
        top_k: int = 4,
        similarity_threshold: float = 0.45
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Perform vector similarity search strictly scoped by organization_id.
        Handles PostgreSQL pgvector native operator (<=> cosine distance) or
        fallback in-memory cosine comparison for SQLite test environments.
        """
        bind = self.session.get_bind()
        is_postgres = bind.dialect.name == "postgresql"

        if is_postgres:
            # Native pgvector cosine distance: 1 - (embedding <=> :vec)
            # cosine distance operator is <=>
            stmt = select(
                DocumentChunk,
                (1.0 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity")
            ).where(
                DocumentChunk.organization_id == organization_id
            ).order_by(
                DocumentChunk.embedding.cosine_distance(query_embedding)
            ).limit(top_k)

            result = await self.session.execute(stmt)
            rows = result.all()
            # Filter by similarity threshold
            filtered = [(chunk, float(sim)) for chunk, sim in rows if sim is not None and sim >= similarity_threshold]
            return filtered
        else:
            # Fallback for SQLite / non-pgvector environments
            stmt = select(DocumentChunk).where(DocumentChunk.organization_id == organization_id)
            result = await self.session.execute(stmt)
            all_chunks = result.scalars().all()

            scored: List[Tuple[DocumentChunk, float]] = []
            for chunk in all_chunks:
                emb = chunk.embedding
                if emb:
                    sim = cosine_similarity(query_embedding, emb)
                    if sim >= similarity_threshold:
                        scored.append((chunk, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]


class QueryLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        organization_id: str,
        question: str,
        model_used: str,
        cache_hit: bool,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        latency_ms: float,
        user_id: Optional[str] = None
    ) -> QueryLog:
        log = QueryLog(
            user_id=user_id,
            organization_id=organization_id,
            question=question,
            model_used=model_used,
            cache_hit=cache_hit,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_org_stats(self, organization_id: str) -> Dict[str, Any]:
        """Aggregate stats for an organization."""
        # Total queries, cache hits, gemini calls, tokens, cost, latency
        stmt = select(
            func.count(QueryLog.id).label("total_queries"),
            func.sum(func.cast(QueryLog.cache_hit, Integer)).label("cache_hits"),
            func.sum(QueryLog.input_tokens).label("total_input_tokens"),
            func.sum(QueryLog.output_tokens).label("total_output_tokens"),
            func.sum(QueryLog.estimated_cost).label("total_cost"),
            func.avg(QueryLog.latency_ms).label("avg_latency")
        ).where(QueryLog.organization_id == organization_id)

        result = await self.session.execute(stmt)
        row = result.one()

        total_queries = row.total_queries or 0
        cache_hits = row.cache_hits or 0
        cache_hit_rate = (cache_hits / total_queries * 100.0) if total_queries > 0 else 0.0
        gemini_calls = total_queries - cache_hits

        # Count total users
        user_count_stmt = select(func.count(User.id)).where(User.organization_id == organization_id)
        user_res = await self.session.execute(user_count_stmt)
        total_users = user_res.scalar() or 0

        # Organization name
        org_stmt = select(Organization.name).where(Organization.id == organization_id)
        org_name = (await self.session.execute(org_stmt)).scalar() or "Unknown"

        return {
            "organization_name": org_name,
            "organization_id": organization_id,
            "total_users": total_users,
            "total_queries": total_queries,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "gemini_calls": gemini_calls,
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
            "estimated_gemini_cost": round(float(row.total_cost or 0.0), 6),
            "average_latency_ms": round(float(row.avg_latency or 0.0), 2)
        }

    async def get_user_stats(self, organization_id: str) -> List[Dict[str, Any]]:
        """User-wise analytics for organization."""
        # Join users with query_logs
        stmt = select(
            User.employee_id,
            User.name,
            User.email,
            func.count(QueryLog.id).label("total_queries"),
            func.sum(func.cast(QueryLog.cache_hit, Integer)).label("cache_hits"),
            func.sum(QueryLog.input_tokens + QueryLog.output_tokens).label("tokens_used"),
            func.sum(QueryLog.estimated_cost).label("estimated_cost"),
            func.avg(QueryLog.latency_ms).label("avg_latency")
        ).outerjoin(
            QueryLog, (User.id == QueryLog.user_id) & (QueryLog.organization_id == organization_id)
        ).where(
            User.organization_id == organization_id
        ).group_by(
            User.id, User.employee_id, User.name, User.email
        ).order_by(desc("total_queries"))

        result = await self.session.execute(stmt)
        user_stats = []
        for r in result.all():
            total = r.total_queries or 0
            hits = r.cache_hits or 0
            calls = total - hits
            user_stats.append({
                "employee_id": r.employee_id,
                "name": r.name,
                "email": r.email,
                "total_queries": total,
                "cache_hits": hits,
                "gemini_calls": calls,
                "tokens_used": r.tokens_used or 0,
                "estimated_cost": round(float(r.estimated_cost or 0.0), 6),
                "avg_latency": round(float(r.avg_latency or 0.0), 2)
            })
        return user_stats

    async def get_usage_summary(self, organization_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Recent query activity summary."""
        stmt = select(
            QueryLog, User.name, User.employee_id
        ).outerjoin(
            User, QueryLog.user_id == User.id
        ).where(
            QueryLog.organization_id == organization_id
        ).order_by(desc(QueryLog.created_at)).limit(limit)

        result = await self.session.execute(stmt)
        summaries = []
        for log, uname, empid in result.all():
            summaries.append({
                "id": log.id,
                "question": log.question,
                "model_used": log.model_used,
                "cache_hit": log.cache_hit,
                "tokens": log.input_tokens + log.output_tokens,
                "cost": round(log.estimated_cost, 6),
                "latency_ms": round(log.latency_ms, 2),
                "user_name": uname or "Unknown",
                "employee_id": empid or "N/A",
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        return summaries


class TelegramSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_session(self, telegram_user_id: int) -> Optional[TelegramSession]:
        stmt = select(TelegramSession).where(TelegramSession.telegram_user_id == telegram_user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_session(
        self,
        telegram_user_id: int,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        role: Optional[str] = None,
        auth_state: str = "UNAUTHENTICATED",
        auth_context: Optional[Dict[str, Any]] = None
    ) -> TelegramSession:
        existing = await self.get_session(telegram_user_id)
        if existing:
            if user_id is not None:
                existing.user_id = user_id
            if organization_id is not None:
                existing.organization_id = organization_id
            if role is not None:
                existing.role = role
            existing.auth_state = auth_state
            if auth_context is not None:
                existing.auth_context = auth_context
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            new_session = TelegramSession(
                telegram_user_id=telegram_user_id,
                user_id=user_id,
                organization_id=organization_id,
                role=role,
                auth_state=auth_state,
                auth_context=auth_context or {}
            )
            self.session.add(new_session)
            await self.session.commit()
            await self.session.refresh(new_session)
            return new_session

    async def delete_session(self, telegram_user_id: int) -> bool:
        stmt = delete(TelegramSession).where(TelegramSession.telegram_user_id == telegram_user_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
