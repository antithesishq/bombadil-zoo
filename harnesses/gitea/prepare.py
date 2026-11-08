def prepare():
    machine.succeed(
        "sed -E '/^(SECRET_KEY|INTERNAL_TOKEN|JWT_SECRET|PASSWD)[[:space:]]*=/s/=.*/= <redacted>/' "
        "/var/lib/gitea/custom/conf/app.ini > /tmp/artifacts/gitea.ini",
        "grep -E '^(DB_TYPE|PATH|INSTALL_LOCK)[[:space:]]*=' /tmp/artifacts/gitea.ini",
    )
    machine.succeed(
        "su -l gitea -c 'GITEA_WORK_DIR=/var/lib/gitea gitea admin user create "
        "--username fixture --password zoo-fixture-password "
        "--email fixture@example.test --must-change-password=false'"
    )
    machine.succeed(
        "curl --fail --silent --show-error -X POST "
        "http://fixture:zoo-fixture-password@127.0.0.1:3000/api/v1/user/repos "
        "-H 'Accept: application/json' -H 'Content-Type: application/json' "
        "-d '{\"name\":\"zoo-repo\",\"description\":\"Disposable browser fuzz fixture\","
        "\"auto_init\":true,\"default_branch\":\"main\",\"readme\":\"Default\",\"private\":false}' "
        "> /tmp/artifacts/repository.json"
    )
    machine.succeed("rm -rf /tmp/gitea-seed")
    machine.succeed(
        "git clone --quiet http://fixture:zoo-fixture-password@127.0.0.1:3000/fixture/zoo-repo.git "
        "/tmp/gitea-seed",
        "git -C /tmp/gitea-seed config user.name 'Fixture User'",
        "git -C /tmp/gitea-seed config user.email fixture@example.test",
    )
    machine.succeed(
        "mkdir -p /tmp/gitea-seed/docs /tmp/gitea-seed/src",
        "cat > /tmp/gitea-seed/README.md <<'EOF'\n"
        "# Bombadil Gitea fixture\n\n"
        "This disposable repository exercises real repository, issue and settings pages.\n\n"
        "See [the guide](docs/guide.md) and the small Python example.\n"
        "EOF",
        "cat > /tmp/gitea-seed/docs/guide.md <<'EOF'\n"
        "# Fixture guide\n\n"
        "Browse files, commits, branches and issues. Nothing here is production data.\n"
        "EOF",
        "cat > /tmp/gitea-seed/src/hello.py <<'EOF'\n"
        "def greet(name: str) -> str:\n"
        "    return f'Hello, {name}!'\n"
        "EOF",
        "git -C /tmp/gitea-seed add README.md docs/guide.md src/hello.py",
        "git -C /tmp/gitea-seed commit --quiet -m 'Seed browser fixture'",
        "git -C /tmp/gitea-seed push --quiet origin main",
        "rm -rf /tmp/gitea-seed",
    )
    machine.succeed(
        "curl --fail --silent --show-error -X POST "
        "http://fixture:zoo-fixture-password@127.0.0.1:3000/api/v1/repos/fixture/zoo-repo/issues "
        "-H 'Accept: application/json' -H 'Content-Type: application/json' "
        "-d '{\"title\":\"Review seeded documentation\","
        "\"body\":\"A harmless issue for browser exploration. Read the fixture guide and leave feedback.\"}' "
        "> /tmp/artifacts/issue.json"
    )
    machine.succeed(
        "curl --fail --silent --show-error -X POST "
        "http://fixture:zoo-fixture-password@127.0.0.1:3000/api/v1/repos/fixture/zoo-repo/issues "
        "-H 'Accept: application/json' -H 'Content-Type: application/json' "
        "-d '{\"title\":\"Closed fixture task\",\"body\":\"A completed item for issue filters.\",\"closed\":true}' "
        "> /tmp/artifacts/closed-issue.json"
    )
