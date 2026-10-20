import ast

import pytest

from future.cli import StubMaker


def test_scaffold_includes_application_layers_and_inline_routes(tmp_path):
    project = tmp_path / "example"
    StubMaker().scaffold_project(project)

    assert (project / "app" / "authentication").is_dir()
    assert (project / "app" / "interfaces").is_dir()
    assert (project / "app" / "repositories").is_dir()
    assert (project / "app" / "services").is_dir()

    route_source = (project / "app" / "routes.py").read_text()
    assert "openapi_routes" not in route_source
    tree = ast.parse(route_source)
    route_names = {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options", "WebSocket"}
    route_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in route_names]
    assert route_calls
    assert all(node.lineno == node.end_lineno for node in route_calls)


def test_new_layer_generators(tmp_path, monkeypatch):
    project = tmp_path / "example"
    StubMaker().scaffold_project(project)
    monkeypatch.chdir(project)

    assert StubMaker().make("service", "User").endswith("app/services/UserService.py")
    assert StubMaker().make("repository", "User").endswith("app/repositories/UserRepository.py")
    interface_path = StubMaker().make("interface", "UserRepository")
    assert interface_path.endswith("app/interfaces/IUserRepository.py")
    assert "class IUserRepository(Interface):" in (project / interface_path).read_text()
    assert StubMaker().make("authentication", "Company").endswith("app/authentication/CompanyAuthentication.py")

    with pytest.raises(ValueError, match="I prefix is reserved"):
        StubMaker().make("repository", "IAccountRepository")
