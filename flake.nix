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
            export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/setic_qualidade"

            if [ ! -d ".venv" ]; then
              uv venv .venv
            fi
            source .venv/bin/activate
            uv pip install -e ".[dev]" --quiet
          '';
        };
      }
    );
}
