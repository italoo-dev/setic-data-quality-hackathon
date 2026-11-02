{
  description = "Plataforma Centralizada de Qualidade, Normalização e Gestão de Dados - SETIC/CAGD";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        # Leitura e parsing dinâmico de pyproject.toml como Fonte Única da Verdade (Single Source of Truth)
        pyprojectData = builtins.fromTOML (builtins.readFile ./pyproject.toml);
        projectName = pyprojectData.project.name;
        projectVersion = pyprojectData.project.version;

        # Validação de metadados via pyproject-nix
        pyprojectParsed = pyproject-nix.lib.project.loadPyproject {
          projectRoot = ./.;
        };

        # Python 3.12 com ferramentas nativas
        python = pkgs.python312;
      in
      {
        # Derivação do pacote baseada no pyproject.toml
        packages.default = pkgs.stdenv.mkDerivation {
          pname = projectName;
          version = projectVersion;
          src = ./.;

          nativeBuildInputs = [
            python
            pkgs.uv
            pkgs.pkg-config
            pkgs.gcc
          ];

          buildPhase = ''
            echo "Construindo ${projectName} v${projectVersion} a partir do pyproject.toml"
          '';

          installPhase = ''
            mkdir -p $out/bin $out/lib
            cp -r app panel pyproject.toml $out/lib/
          '';
        };

        # Shell de desenvolvimento reprodutível e simplificado
        devShells.default = pkgs.mkShell {
          name = "${projectName}-devshell";

          buildInputs = [
            # Runtime Python e empacotamento declarativo
            python
            pkgs.uv

            # LSPs e Linters estáticos
            pkgs.ruff
            pkgs.pyright

            # Compilação nativa para extensões C++
            pkgs.gcc
            pkgs.pkg-config
            pkgs.zlib

            # Ferramentas auxiliares
            pkgs.git
            pkgs.curl
          ];

          shellHook = ''
            echo "====================================================================="
            echo " SETIC/CAGD - Plataforma de Qualidade e Normalização de Dados"
            echo " Ambiente Nix Simplificado: ${system} | Python 3.12"
            echo " Banco de Dados: Container Docker / Podman (PostgreSQL 16)"
            echo " Single Source of Truth: pyproject.toml (v${projectVersion})"
            echo "====================================================================="

            # 1. Configurações de Ambiente
            export REPO_ROOT="$(pwd)"
            export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/setic_qualidade"
            export PYTHONPATH="$REPO_ROOT"
            mkdir -p "$REPO_ROOT/.cache"

            # 2. Sincronização do Ambiente Virtual a partir de pyproject.toml via uv
            if [ ! -d ".venv" ]; then
              echo "[ENV] Criando ambiente virtual Python (.venv)..."
              uv venv .venv --quiet
            fi
            source .venv/bin/activate

            echo "[ENV] Sincronizando dependências declaradas no pyproject.toml..."
            uv pip install -e ".[dev]" --quiet

            # 3. Gerenciamento do Banco de Dados via Container (Docker / Podman)
            iniciar-db() {
              if command -v podman > /dev/null 2>&1; then
                echo "[DB] Iniciando container PostgreSQL 16 via Podman..."
                podman run -d --name setic_postgres --replace \
                  -e POSTGRES_DB=setic_qualidade \
                  -e POSTGRES_USER=postgres \
                  -e POSTGRES_PASSWORD=postgres \
                  -p 5432:5432 \
                  -v setic_postgres_data:/var/lib/postgresql/data \
                  docker.io/library/postgres:16-alpine > /dev/null 2>&1
                echo "[DB] Container PostgreSQL pronto na porta 5432."
              elif command -v docker > /dev/null 2>&1; then
                echo "[DB] Iniciando container PostgreSQL 16 via Docker..."
                docker run -d --name setic_postgres \
                  -e POSTGRES_DB=setic_qualidade \
                  -e POSTGRES_USER=postgres \
                  -e POSTGRES_PASSWORD=postgres \
                  -p 5432:5432 \
                  -v setic_postgres_data:/var/lib/postgresql/data \
                  docker.io/library/postgres:16-alpine > /dev/null 2>&1 || docker start setic_postgres > /dev/null 2>&1
                echo "[DB] Container PostgreSQL pronto na porta 5432."
              else
                echo "[DB] Nem Podman nem Docker encontrados. Use docker-compose up -d manualmente."
              fi
            }

            parar-db() {
              echo "[DB] Encerrando container PostgreSQL..."
              if command -v podman > /dev/null 2>&1; then
                podman stop setic_postgres > /dev/null 2>&1 || true
              elif command -v docker > /dev/null 2>&1; then
                docker stop setic_postgres > /dev/null 2>&1 || true
              fi
              echo "[DB] Container encerrado."
            }

            # 4. Aliases de Operação Rápida
            alias iniciar-api="uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
            alias iniciar-painel="streamlit run panel/app.py --server.port 8501 --server.address 0.0.0.0"
            alias verificar-codigo="ruff check . && ruff format --check . && pyright"
            alias testar-pipeline="pytest tests/ -v"

            iniciar-tudo() {
              echo "[SETIC] Inicializando container do banco de dados..."
              iniciar-db
              sleep 1.5
              echo "[SETIC] Iniciando API FastAPI (8000) e Painel Streamlit (8501)..."
              uvicorn app.main:app --host 0.0.0.0 --port 8000 &
              PID_API=$!
              streamlit run panel/app.py --server.port 8501 --server.address 0.0.0.0 &
              PID_STREAMLIT=$!
              echo "Serviços rodando: API (PID $PID_API), Painel (PID $PID_STREAMLIT)"
              echo "Pressione Ctrl+C para encerrar ambos."
              trap "kill $PID_API $PID_STREAMLIT; exit" INT TERM
              wait
            }

            echo ""
            echo "Comandos disponíveis:"
            echo "  iniciar-db       -> Inicia o container PostgreSQL 16 (Podman/Docker)"
            echo "  parar-db         -> Encerra o container PostgreSQL"
            echo "  iniciar-api      -> Inicia o servidor FastAPI (http://localhost:8000/docs)"
            echo "  iniciar-painel   -> Inicia o Dashboard Streamlit (http://localhost:8501)"
            echo "  iniciar-tudo     -> Inicia container DB, API e Painel concorrentemente"
            echo "  verificar-codigo -> Executa ruff e pyright conforme diretrizes de AGENTS.md"
            echo "  testar-pipeline  -> Executa a suíte de testes do motor de qualidade"
            echo "====================================================================="
          '';
        };
      }
    );
}
