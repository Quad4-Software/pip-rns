# pip-rns bash completion
_pip_rns() {
    local cur prev words cword
    _init_completion || return

    local commands="install update list uninstall alias index"
    local install_opts="--pipx --uv --poetry --ref --editable --use-cache --venv --no-color --config"
    local alias_commands="add set rm ls"
    local index_commands="add rm ls sync list search"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        return
    fi

    case "${words[1]}" in
        install|update)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "$install_opts" -- "$cur"))
            fi
            ;;
        alias)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "$alias_commands" -- "$cur"))
            fi
            ;;
        index)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "$index_commands" -- "$cur"))
            fi
            ;;
    esac
} && complete -F _pip_rns pip-rns

# pipx-rns bash completion
_pipx_rns() {
    local cur prev words cword
    _init_completion || return

    local commands="install inject update list uninstall"
    local install_opts="--ref --editable --use-cache --no-color --config"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        return
    fi

    case "${words[1]}" in
        install|update)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "$install_opts" -- "$cur"))
            fi
            ;;
        inject)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "--ref --use-cache" -- "$cur"))
            fi
            ;;
    esac
} && complete -F _pipx_rns pipx-rns
