from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.main import app
from app.models.article_model import ArticleModel
from app.services.article_services import get_articles as legacy_get_articles
from app.services.article_services import get_published_articles, get_admin_articles, update_article_publication

client = TestClient(app)


def _article_session():
    engine = create_engine("sqlite:///:memory:")
    ArticleModel.__table__.create(engine)
    return Session(engine)


def test_article_publication_archive_is_reversible(monkeypatch):
    db = _article_session()
    db.add_all(
        [
            ArticleModel(
                title="Informasi Toko",
                description="Jam operasional dan layanan resmi.",
                display_id=1,
                is_published=True,
            ),
            ArticleModel(
                title="Placeholder Info",
                description="Informasi sementara.",
                display_id=2,
                is_published=True,
            ),
        ]
    )
    db.commit()

    update_module = __import__(
        "app.services.article_services.update_article",
        fromlist=["delete_cache_by_pattern"],
    )
    monkeypatch.setattr(update_module, "delete_cache_by_pattern", lambda _pattern: None)

    placeholder = db.query(ArticleModel).filter_by(title="Placeholder Info").one()
    archived = update_article_publication(db, placeholder.id, False).unwrap()
    assert archived.data.is_published is False
    assert [item.title for item in get_published_articles(db).unwrap().data] == ["Informasi Toko"]

    admin_titles = [item.title for item in get_admin_articles(db).unwrap().data]
    assert admin_titles == ["Informasi Toko", "Placeholder Info"]

    restored = update_article_publication(db, placeholder.id, True).unwrap()
    assert restored.data.is_published is True
    assert [item.title for item in get_published_articles(db).unwrap().data] == [
        "Informasi Toko",
        "Placeholder Info",
    ]
    db.close()


def test_legacy_article_feed_response_shape_remains_unchanged():
    db = _article_session()
    db.add(
        ArticleModel(
            title="Info Publik",
            description="Konten lama tetap tersedia.",
            display_id=1,
            is_published=True,
        )
    )
    db.commit()

    response = legacy_get_articles(db).unwrap()
    data = response.model_dump()
    assert set(data) == {"status_code", "message", "data"}
    assert set(data["data"][0]) == {"id", "display_id", "title", "img", "description_list"}
    db.close()


def test_archive_management_routes_require_admin_authentication():
    list_response = client.get("/articles/admin/all")
    update_response = client.patch(
        "/articles/1/publication",
        json={"is_published": False},
    )

    assert list_response.status_code == 403
    assert update_response.status_code == 403
