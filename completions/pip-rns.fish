# pip-rns fish completion

function __fish_pip_rns_using_command
    set -l cmd (commandline -opc)
    set -e cmd[1]
    if test (count $cmd) -ge 1
        contains -- $cmd[1] $argv
    end
end

# top-level commands
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a install -d "Install a package from a remote"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a update -d "Reinstall a package from a remote"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a list -d "List installed packages"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a uninstall -d "Uninstall a package"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a alias -d "Manage local aliases"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a index -d "Manage remote package indexes"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a release -d "List and view releases"
complete -c pip-rns -f -n "test (count (commandline -opc)) = 1" -a bundle -d "Install or verify offline .opip bundles"

# global flags
complete -c pip-rns -l no-color -d "Disable colored output"
complete -c pip-rns -l config -r -d "Config directory for aliases and indexes"

# install/update flags
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l pipx -d "Use pipx instead of pip"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l uv -d "Use uv instead of pip"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l poetry -d "Use poetry add instead of pip"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l ref -r -d "Git tag, branch or commit"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -s e -l editable -d "Install in editable mode"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l use-cache -d "Cache clone locally"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l from-release -d "Install from release .whl"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -s s -l from-source -d "Force clone/install from source"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l require-release -d "Require a release wheel"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l verify -r -d "Require release signed by identity"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l insecure -d "Allow install when verification is not confirmed"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l offline -d "Use local cache / paths only"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -s y -l yes -d "Skip expensive-clone prompts"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -s f -l force -d "Reinstall over an existing install"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l update -d "Update to the latest ref"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l upgrade -d "Update to the latest ref"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l remember-venv -d "Remember --venv for this remote"
complete -c pip-rns -n "__fish_pip_rns_using_command install update" -l forget-venv -d "Forget remembered venv for this remote"
complete -c pip-rns -n "__fish_pip_rns_using_command install" -l venv -r -d "Install into a virtualenv at PATH"

# alias subcommands
complete -c pip-rns -n "__fish_pip_rns_using_command alias" -f -a add -d "Create an alias"
complete -c pip-rns -n "__fish_pip_rns_using_command alias" -f -a set -d "Create or update an alias"
complete -c pip-rns -n "__fish_pip_rns_using_command alias" -f -a rm -d "Remove an alias"
complete -c pip-rns -n "__fish_pip_rns_using_command alias" -f -a ls -d "List all aliases"

# index subcommands
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a add -d "Register an index URL"
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a rm -d "Remove and re-sync an index"
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a ls -d "List registered indexes"
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a sync -d "Clone/pull all indexes and cache package names"
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a list -d "List all available packages from synced indexes"
complete -c pip-rns -n "__fish_pip_rns_using_command index" -f -a search -d "Search packages by name across synced indexes"

# release subcommands
complete -c pip-rns -n "__fish_pip_rns_using_command release" -f -a list -d "List releases on a remote repo"
complete -c pip-rns -n "__fish_pip_rns_using_command release" -f -a view -d "View release details"

# bundle subcommands
complete -c pip-rns -n "__fish_pip_rns_using_command bundle" -f -a install -d "Install a .opip bundle"
complete -c pip-rns -n "__fish_pip_rns_using_command bundle" -f -a verify -d "Verify a .opip bundle"
complete -c pip-rns -n "__fish_pip_rns_using_command bundle install" -l signer -r -d "Required signer identity"
complete -c pip-rns -n "__fish_pip_rns_using_command bundle install" -l require-signature -d "Fail if unsigned"
complete -c pip-rns -n "__fish_pip_rns_using_command bundle install" -l user -d "User install"
complete -c pip-rns -n "__fish_pip_rns_using_command bundle install" -l replace -d "Force reinstall"

# pipx-rns completions
complete -c pipx-rns -f -n "test (count (commandline -opc)) = 1" -a install -d "Install a package from a remote via pipx"
complete -c pipx-rns -f -n "test (count (commandline -opc)) = 1" -a inject -d "Inject a package into an existing pipx venv"
complete -c pipx-rns -f -n "test (count (commandline -opc)) = 1" -a update -d "Force-reinstall a package via pipx"
complete -c pipx-rns -f -n "test (count (commandline -opc)) = 1" -a list -d "List pipx-installed packages"
complete -c pipx-rns -f -n "test (count (commandline -opc)) = 1" -a uninstall -d "Uninstall a pipx-installed package"

complete -c pipx-rns -l no-color -d "Disable colored output"
complete -c pipx-rns -l config -r -d "Config directory"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l ref -r -d "Git tag, branch or commit"
complete -c pipx-rns -n "__fish_pip_rns_using_command install" -s e -l editable -d "Install in editable mode"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update inject" -l use-cache -d "Cache clone locally"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l from-release -d "Install from release .whl"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -s s -l from-source -d "Force clone/install from source"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l require-release -d "Require a release wheel"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l verify -r -d "Require release signed by identity"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l insecure -d "Allow install when verification is not confirmed"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update inject" -l offline -d "Use local cache / paths only"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update inject" -s y -l yes -d "Skip expensive-clone prompts"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -s f -l force -d "Reinstall over an existing install"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l update -d "Update to the latest ref"
complete -c pipx-rns -n "__fish_pip_rns_using_command install update" -l upgrade -d "Update to the latest ref"
