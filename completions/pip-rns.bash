# pip-rns bash completion
_pip_rns() {
    local cur prev words cword
    _init_completion || return

    local commands="install update list uninstall alias index release bundle"
    local install_opts="--pipx --uv --poetry --ref --editable --use-cache --venv --from-release --verify --no-color --config"
    local alias_commands="add set rm ls"
    local index_commands="add rm ls sync list search"
    local release_commands="list view"

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
            release)
                if [[ $cword -eq 2 ]]; then
                    COMPREPLY=($(compgen -W "$release_commands" -- "$cur"))
                fi
                ;;
            bundle)
                if [[ $cword -eq 2 ]]; then
                    COMPREPLY=($(compgen -W "install verify" -- "$cur"))
                fi
                ;;
    esac
} && complete -F _pip_rns pip-rns

# pipx-rns bash completion
_pipx_rns() {
    local cur prev words cword
    _init_completion || return

    local commands="install inject update list uninstall"
    local install_opts="--ref --editable --use-cache --from-release --verify --no-color --config"

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
