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

        # Integração com pyproject-nix para validação de metadados
        pyprojectParsed = pyproject-nix.lib.project.loadPyproject {
          projectRoot = ./.;
        };

        # Python 3.12 com ferramentas nativas de compilação
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

        # Shell de desenvolvimento reprodutível
        devShells.default = pkgs.mkShell {
          name = "${projectName}-devshell";

          buildInputs = [
            # Runtime Python e gerenciador de pacotes dinâmico
            python
            pkgs.uv

            # Servidor e utilitários PostgreSQL 16
            pkgs.postgresql_16

            # LSPs e Linters estáticos
            pkgs.ruff
            pkgs.pyright

            # Compilação nativa para extensões C++ (RapidFuzz, Psycopg, etc.)
            pkgs.gcc
            pkgs.pkg-config
            pkgs.zlib

            # Ferramentas auxiliares
            pkgs.git
            pkgs.curl
            pkgs.which
          ];

          shellHook = ''
            echo "====================================================================="
            echo " SETIC/CAGD - Plataforma de Qualidade e Normalização de Dados"
            echo " Ambiente Nix Carregado: ${system} | Python 3.12"
            echo " Single Source of Truth: pyproject.toml (v${projectVersion})"
            echo "====================================================================="

            # 1. Configuração do Diretório Isolado do PostgreSQL Local
            export REPO_ROOT="$(pwd)"
            export PGDATA="$REPO_ROOT/.postgres/data"
            export PGSOCKET="$REPO_ROOT/.postgres/sockets"
            export PGLOGS="$REPO_ROOT/.postgres/logs"
            export PGPORT="5433"
            export PGHOST="$PGSOCKET"
            export DATABASE_URL="postgresql+psycopg://postgres@localhost:$PGPORT/setic_qualidade"
            export PYTHONPATH="$REPO_ROOT"

            mkdir -p "$PGDATA" "$PGSOCKET" "$PGLOGS" "$REPO_ROOT/.cache"

            # 2. Inicialização do Banco PostgreSQL se inexistente
            if [ ! -f "$PGDATA/PG_VERSION" ]; then
              echo "[DB] Inicializando cluster PostgreSQL local em $PGDATA..."
              initdb -U postgres -D "$PGDATA" --auth=trust --no-locale --encoding=UTF8 > /dev/null 2>&1
              echo "unix_socket_directories = '$PGSOCKET'" >> "$PGDATA/postgresql.conf"
              echo "port = $PGPORT" >> "$PGDATA/postgresql.conf"
              echo "listen_addresses = '127.0.0.1'" >> "$PGDATA/postgresql.conf"
            fi

            # 3. Inicialização do Daemon PostgreSQL
            if ! pg_isready -h "$PGSOCKET" -p "$PGPORT" > /dev/null 2>&1; then
              echo "[DB] Iniciando serviço PostgreSQL (Porta $PGPORT)..."
              pg_ctl -D "$PGDATA" -l "$PGLOGS/postgresql.log" -o "-k $PGSOCKET -p $PGPORT" start > /dev/null 2>&1
              sleep 1
            fi

            # 4. Criação da Base de Dados caso não exista
            if ! psql -h "$PGSOCKET" -p "$PGPORT" -U postgres -lqt | cut -d \| -f 1 | grep -qw setic_qualidade; then
              echo "[DB] Criando banco de dados 'setic_qualidade'..."
              createdb -h "$PGSOCKET" -p "$PGPORT" -U postgres setic_qualidade
            fi

            # 5. Sincronização do Ambiente Virtual a partir de pyproject.toml via uv
            if [ ! -d ".venv" ]; then
              echo "[ENV] Criando ambiente virtual Python (.venv)..."
              uv venv .venv --quiet
            fi
            source .venv/bin/activate

            echo "[ENV] Sincronizando dependências declaradas no pyproject.toml..."
            uv pip install -e ".[dev]" --quiet

            # 6. Aliases de Operação Rápida
            alias iniciar-api="uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
            alias iniciar-painel="streamlit run panel/app.py --server.port 8501 --server.address 0.0.0.0"
            alias parar-db="pg_ctl -D \"\$PGDATA\" stop"
            alias iniciar-db="pg_ctl -D \"\$PGDATA\" -l \"\$PGLOGS/postgresql.log\" -o \"-k \$PGSOCKET -p \$PGPORT\" start"
            alias verificar-codigo="ruff check . && ruff format --check . && pyright"
            alias testar-pipeline="pytest tests/ -v"

            iniciar-tudo() {
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
            echo "  iniciar-api      -> Inicia o servidor FastAPI (http://localhost:8000/docs)"
            echo "  iniciar-painel   -> Inicia o Dashboard Streamlit (http://localhost:8501)"
            echo "  iniciar-tudo     -> Inicia ambos os serviços concorrentemente"
            echo "  verificar-codigo -> Executa ruff e pyright conforme diretrizes de AGENTS.md"
            echo "  testar-pipeline  -> Executa a suíte de testes do motor de qualidade"
            echo "====================================================================="
          '';
        };
      }
    );
}
