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
        pkgs = import nixpkgs { inherit system; config.allowUnfree = true; };
        pyproject = builtins.fromTOML (builtins.readFile ./pyproject.toml);
        _ = pyproject-nix.lib.project.loadPyproject { projectRoot = ./.; };
      in
      {
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
          ];

          shellHook = ''
            export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/setic_qualidade"
            [ ! -d ".venv" ] && uv venv .venv
            source .venv/bin/activate
            uv pip install -e ".[dev]" --quiet
          '';
        };
      }
    );
}
