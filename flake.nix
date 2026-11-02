{
  description = "Plataforma Centralizada de Qualidade, Normalização e Gestão de Dados - SETIC/CAGD";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, git-hooks }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; config.allowUnfree = true; };
        pyproject = builtins.fromTOML (builtins.readFile ./pyproject.toml);
        _ = pyproject-nix.lib.project.loadPyproject { projectRoot = ./.; };

        pre-commit-check = git-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            ruff.enable = true;
            ruff-format.enable = true;
          };
        };
      in
      {
        checks = {
          inherit pre-commit-check;
        };
        packages.default = pkgs.stdenv.mkDerivation {
          pname = pyproject.project.name;
          version = pyproject.project.version;
          src = ./.;
          nativeBuildInputs = with pkgs; [ python312 uv pkg-config gcc ];
          buildPhase = "true";
          installPhase = ''
            mkdir -p $out/lib
            cp -r app panel pyproject.toml $out/lib/
          '';
        };

        devShells.default = pkgs.mkShell {
          name = "${pyproject.project.name}-devshell";
          buildInputs = pre-commit-check.enabledPackages;
          packages = with pkgs; [
            python312
            uv
            ruff
            pyright
            gcc
            pkg-config
            zlib
            git
            curl
            podman-compose
          ];

          shellHook = ''
            ${pre-commit-check.shellHook}
            export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/setic_qualidade"
            if [ ! -f ".venv/bin/activate" ] || ! .venv/bin/python -c "import sys" 2>/dev/null; then
              rm -rf .venv
              uv venv .venv
              uv pip install -e ".[dev]" --quiet
            fi
            export VIRTUAL_ENV="$PWD/.venv"
            export PATH="$VIRTUAL_ENV/bin:$PATH"
          '';
        };
      }
    );
}
