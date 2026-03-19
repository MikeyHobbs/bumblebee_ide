from __future__ import annotations

"""Post, Comment models and query builder."""

from core.base_model import BaseModel
from models.user_model import User


class Post(BaseModel):
    """A blog post with publication state.

    Attributes:
        title: The post title.
        content: The post body text.
        author_id: The id of the User who authored this post.
        published: Whether the post has been published.
        slug: URL-friendly version of the title.
    """

    def __init__(self, title: str, content: str, author_id: str) -> None:
        """Initialize a new Post.

        Args:
            title: The post title.
            content: The post body text.
            author_id: The id of the authoring User.
        """
        super().__init__()
        self.title: str = title
        self.content: str = content
        self.author_id: str = author_id
        self.published: bool = False
        self.slug: str = ""

    def publish(self) -> None:
        """Mark the post as published and persist the change."""
        self.published = True
        self.save()


class Comment(BaseModel):
    """A comment on a post.

    Attributes:
        text: The comment body.
        post_id: The id of the Post this comment belongs to.
        user_id: The id of the User who wrote the comment.
        flagged: Whether the comment has been flagged for review.
    """

    def __init__(self, text: str, post_id: str, user_id: str) -> None:
        """Initialize a new Comment.

        Args:
            text: The comment body.
            post_id: The id of the parent Post.
            user_id: The id of the commenting User.
        """
        super().__init__()
        self.text: str = text
        self.post_id: str = post_id
        self.user_id: str = user_id
        self.flagged: bool = False

    def flag(self) -> None:
        """Flag this comment for moderation review."""
        self.flagged = True


class QueryBuilder:
    """A chainable query builder for filtering, ordering, and limiting collections.

    Attributes:
        _items: The source list of objects to query against.
        _filters: Accumulated (key, value) filter pairs.
        _order: The attribute name to sort by, or None.
        _limit_val: Maximum number of results to return, or None.
    """

    def __init__(self, items: list) -> None:
        """Initialize the query builder with a list of items.

        Args:
            items: The source collection to query.
        """
        self._items: list = items
        self._filters: list = []
        self._order: str | None = None
        self._limit_val: int | None = None

    def filter(self, key: str, value: object) -> QueryBuilder:
        """Add a filter condition to the query.

        Args:
            key: The attribute name to filter on.
            value: The value the attribute must equal.

        Returns:
            self, for method chaining.
        """
        self._filters.append((key, value))
        return self

    def order_by(self, key: str) -> QueryBuilder:
        """Set the attribute to order results by.

        Args:
            key: The attribute name to sort on.

        Returns:
            self, for method chaining.
        """
        self._order = key
        return self

    def limit(self, n: int) -> QueryBuilder:
        """Limit the number of results returned.

        Args:
            n: The maximum number of results.

        Returns:
            self, for method chaining.
        """
        self._limit_val = n
        return self

    def all(self) -> list:
        """Execute the query and return all matching results.

        Returns:
            A list of items matching all filters, ordered and limited as configured.
        """
        results = list(self._items)

        for key, value in self._filters:
            results = [item for item in results if getattr(item, key, None) == value]

        if self._order is not None:
            results.sort(key=lambda item: getattr(item, self._order, ""))

        if self._limit_val is not None:
            results = results[: self._limit_val]

        return results

    def first(self) -> object | None:
        """Execute the query and return the first result.

        Returns:
            The first matching item, or None if no results.
        """
        results = self.all()
        if results:
            return results[0]
        return None


def find_recent_posts(qb: QueryBuilder, days: int) -> list:
    """Find recent published posts using the query builder.

    Args:
        qb: A QueryBuilder instance pre-loaded with post items.
        days: Not used for actual date math here; controls the result limit
              as a proxy (returns at most `days` posts).

    Returns:
        A list of published posts, ordered by title, limited to `days` entries.
    """
    return qb.filter("published", True).order_by("title").limit(days).all()


def paginate_posts(qb: QueryBuilder, page: int, size: int) -> list:
    """Return a page of posts from the query builder.

    Args:
        qb: A QueryBuilder instance pre-loaded with post items.
        page: The 1-based page number.
        size: The number of items per page.

    Returns:
        A list of posts for the requested page, ordered by title.
    """
    all_posts = qb.order_by("title").limit(page * size).all()
    start = (page - 1) * size
    return all_posts[start:]


def summarize_user_activity(user: object, posts: list, comments: list) -> dict:
    """Build an activity summary for a user across posts and comments.

    Args:
        user: A User instance with id, name, and email attributes.
        posts: A list of Post-like objects with an author_id attribute.
        comments: A list of Comment-like objects with a user_id attribute.

    Returns:
        A dict containing user info and counts of their posts and comments.
    """
    user_posts = [p for p in posts if p.author_id == user.id]
    user_comments = [c for c in comments if c.user_id == user.id]

    return {
        "user_id": user.id,
        "user_name": user.name,
        "user_email": user.email,
        "post_count": len(user_posts),
        "comment_count": len(user_comments),
        "total_activity": len(user_posts) + len(user_comments),
    }


def serialize_post(data: dict) -> dict:
    """Serialize a post data dict into a transport-ready format.

    Args:
        data: A dict with "title", "content", and "author_id" keys.

    Returns:
        A dict with trimmed and normalized fields.
    """
    title = data["title"]
    content = data["content"]
    author_id = data["author_id"]

    slug = title.lower().replace(" ", "-").strip("-")
    preview = content[:140] + "..." if len(content) > 140 else content

    return {
        "title": title.strip(),
        "slug": slug,
        "preview": preview,
        "author_id": author_id,
    }


def get_published_posts_by_role(users: list, posts: list, target_role: str) -> list:
    """Get all published posts written by active users with a specific role.

    Args:
        users: A list of User instances.
        posts: A list of Post instances.
        target_role: The role to filter users by (e.g. "admin").

    Returns:
        A list of published Post instances whose authors are active and
        have the target role.
    """
    eligible_ids: set = set()
    for user in users:
        if user.is_active and user.role == target_role:
            eligible_ids.add(user.id)

    result: list = []
    for post in posts:
        if post.author_id in eligible_ids and post.published:
            result.append(post)

    return result
