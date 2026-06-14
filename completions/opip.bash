# opip bash completion
_opip() {
    local cur prev words cword
    _init_completion || return

    local commands="create install uninstall uninstall-file open export update verify keygen info list help register-windows unregister-windows"
    local create_opts="-o -C -r --python --platform --publisher --identity --require-pypi-hash --jobs --no-deps --no-cache --include-project --no-include-project --name --no-interactive"
    local install_opts="--target --user --system --replace --no-verify --signer --require-signature --data-dir --no-color"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        return
    fi

    case "${words[1]}" in
        create)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "$create_opts" -- "$cur"))
            fi
            ;;
        install)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "$install_opts" -- "$cur"))
            fi
            ;;
        verify)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "--signer --require-signature --require-pypi-hash --data-dir --no-color" -- "$cur"))
            fi
            ;;
    esac
} && complete -F _opip opip
