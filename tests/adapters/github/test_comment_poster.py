"""GitHubCommentPoster のテスト。CommentPortの実装。

`gh` CLIをサブプロセスとして呼ぶ(git同様、HTTPクライアント依存を増やさない)。
実際のGitHub APIは叩かず、フェイクのランナーを注入してupsertロジック
(既存コメントの検索→更新 or 新規作成)だけを検証する。

実際にGitHub上でコメントが描画されることの確認は、司令塔指示により
自リポジトリで実PRを立てて別途確認する(このテストの対象外)。
"""

import json

from design_diff.adapters.github.comment_poster import _MARKER, GitHubCommentPoster


class FakeGh:
    """`gh` CLI呼び出しを記録・スタブ化するフェイク。"""

    def __init__(self, existing_comments=None):
        self.existing_comments = existing_comments or []
        self.calls: list[list[str]] = []
        self.posted_bodies: list[str] = []
        self.patched: list[tuple[int, str]] = []

    def __call__(self, args: list[str]):
        self.calls.append(args)

        class _Result:
            def __init__(self, stdout, returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        is_list_call = "-f" in args and args[args.index("-f") + 1] == "per_page=100"
        if is_list_call:
            return _Result(json.dumps(self.existing_comments))

        if "-X" in args and "PATCH" in args:
            comment_id = int(args[1].rsplit("/", 1)[-1])
            body = args[args.index("-f") + 1].removeprefix("body=")
            self.patched.append((comment_id, body))
            return _Result("{}")

        body = args[args.index("-f") + 1].removeprefix("body=")
        self.posted_bodies.append(body)
        return _Result("{}")


class TestGitHubCommentPosterCreate:
    def test_creates_a_new_comment_when_none_exists_yet(self):
        gh = FakeGh(existing_comments=[])
        poster = GitHubCommentPoster(repo="owner/repo", runner=gh)

        poster.upsert(pr=1, body="## design-diff\n\nsomething changed")

        assert len(gh.posted_bodies) == 1
        assert "something changed" in gh.posted_bodies[0]
        assert gh.patched == []

    def test_tags_the_posted_body_with_a_hidden_marker(self):
        """upsertで自分の投稿だと後から見分けられるよう、マーカーを埋め込む。"""
        gh = FakeGh(existing_comments=[])
        poster = GitHubCommentPoster(repo="owner/repo", runner=gh)

        poster.upsert(pr=1, body="body text")

        assert _MARKER in gh.posted_bodies[0]


class TestGitHubCommentPosterUpdate:
    def test_updates_the_existing_marked_comment_instead_of_creating_a_new_one(self):
        gh = FakeGh(
            existing_comments=[
                {"id": 42, "body": f"{_MARKER}\nold content"},
            ]
        )
        poster = GitHubCommentPoster(repo="owner/repo", runner=gh)

        poster.upsert(pr=1, body="new content")

        assert gh.posted_bodies == []
        assert len(gh.patched) == 1
        comment_id, body = gh.patched[0]
        assert comment_id == 42
        assert "new content" in body

    def test_ignores_comments_without_the_marker_and_creates_a_new_one(self):
        """他のツール/人間が書いたコメントを誤って上書きしない。"""
        gh = FakeGh(
            existing_comments=[
                {"id": 99, "body": "a human left a comment here"},
            ]
        )
        poster = GitHubCommentPoster(repo="owner/repo", runner=gh)

        poster.upsert(pr=1, body="new content")

        assert len(gh.posted_bodies) == 1
        assert gh.patched == []
