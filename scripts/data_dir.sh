# Sourced by the other scripts: sets DATA, the folder holding the provided graphs
# (pr_[u|s]<N>_<M>.txt). Run the scripts from the repo root.
#
#   course server : /workspace/coe502/datasets   (used whenever that folder exists)
#   own machines  : ../datasets                  (next to the repo, e.g. ~/COE502_Project/datasets)
#
# DATA=/some/other/folder overrides both.
# The hand-made test graph tiny_dangling.txt is ours and stays in the repo's datasets/.
if [ -z "${DATA:-}" ]; then
    if [ -d /workspace/coe502/datasets ]; then
        DATA=/workspace/coe502/datasets
    else
        DATA=../datasets
    fi
fi
