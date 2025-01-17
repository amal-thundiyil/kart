import logging


from .diff_structs import DatasetDiff, RepoDiff
from .key_filters import DatasetKeyFilter, RepoKeyFilter
from .structure import RepoStructure

L = logging.getLogger("kart.diff_util")


def get_all_ds_paths(
    base_rs: RepoStructure,
    target_rs: RepoStructure,
    repo_key_filter=RepoKeyFilter.MATCH_ALL,
):
    """Returns a list of all dataset paths in either RepoStructure (that match repo_key_filter).

    Args:
        base_rs (kart.structure.RepoStructure)
        target_rs (kart.structure.RepoStructure)
        repo_key_filter (kart.key_filters.RepoKeyFilter): Controls which datasets match and are included in the result.

    Returns:
        Sorted list of all dataset paths in either RepoStructure (that match repo_key_filter).
    """
    base_ds_paths = {ds.path for ds in base_rs.datasets()}
    target_ds_paths = {ds.path for ds in target_rs.datasets()}
    all_ds_paths = base_ds_paths | target_ds_paths

    if not repo_key_filter.match_all:
        all_ds_paths = repo_key_filter.filter_keys(all_ds_paths)

    return sorted(list(all_ds_paths))


def get_repo_diff(
    base_rs,
    target_rs,
    *,
    include_wc_diff=False,
    workdir_diff_cache=None,
    repo_key_filter=RepoKeyFilter.MATCH_ALL,
    convert_to_dataset_format=False,
):
    """
    Generates a RepoDiff containing an entry for every dataset in the repo
    (so long as it matches repo_key_filter and has any changes).

    base_rs, target_rs - kart.structure.RepoStructure objects to diff between.
    include_wc_diff - if True the diff generated will be from base_rs<>working_copy
        (in which case, target_rs must be the HEAD commit which the working copy is tracking).
    workdir_diff_cache - not required, but can be provided if a WorkdirDiffCache is already in use
        to save repeated work.
    repo_key_filter - controls which datasets (and PK values) match and are included in the diff.
    """

    all_ds_paths = get_all_ds_paths(base_rs, target_rs, repo_key_filter)

    if include_wc_diff and workdir_diff_cache is None:
        workdir_diff_cache = target_rs.repo.working_copy.workdir_diff_cache()

    repo_diff = RepoDiff()
    for ds_path in all_ds_paths:
        repo_diff[ds_path] = get_dataset_diff(
            ds_path,
            base_rs.datasets(),
            target_rs.datasets(),
            include_wc_diff=include_wc_diff,
            workdir_diff_cache=workdir_diff_cache,
            ds_filter=repo_key_filter[ds_path],
            convert_to_dataset_format=convert_to_dataset_format,
        )
    # No need to recurse since self.get_dataset_diff already prunes the dataset diffs.
    repo_diff.prune(recurse=False)
    return repo_diff


def get_dataset_diff(
    ds_path,
    base_datasets,
    target_datasets,
    *,
    include_wc_diff=False,
    workdir_diff_cache=None,
    ds_filter=DatasetKeyFilter.MATCH_ALL,
    convert_to_dataset_format=False,
):
    """
    Generates the DatasetDiff for the dataset at path dataset_path.

    base_rs, target_rs - kart.structure.RepoStructure objects to diff between.
    include_wc_diff - if True the diff generated will be from base_rs<>working_copy
        (in which case, target_rs must be the HEAD commit which the working copy is tracking).
    workdir_diff_cache - reusing the same WorkdirDiffCache for every dataset that is being diffed at one time
        is more efficient as it can save FileSystemWorkingCopy.raw_diff_from_index being called multiple times
    ds_filter - controls which PK values match and are included in the diff.
    """
    base_target_diff = None
    target_wc_diff = None

    if base_datasets == target_datasets:
        base_ds = target_ds = base_datasets.get(ds_path)

    else:
        # diff += base_ds<>target_ds
        base_ds = base_datasets.get(ds_path)
        target_ds = target_datasets.get(ds_path)

        if base_ds is not None:
            from_ds, to_ds = base_ds, target_ds
            reverse = False
        else:
            from_ds, to_ds = target_ds, base_ds
            reverse = True

        base_target_diff = from_ds.diff(to_ds, ds_filter=ds_filter, reverse=reverse)
        L.debug("base<>target diff (%s): %s", ds_path, repr(base_target_diff))

    if include_wc_diff:
        # diff += target_ds<>working_copy
        if workdir_diff_cache is None:
            workdir_diff_cache = target_ds.repo.working_copy.workdir_diff_cache()

        if target_ds is not None:
            target_wc_diff = target_ds.diff_to_working_copy(
                workdir_diff_cache,
                ds_filter=ds_filter,
                convert_to_dataset_format=convert_to_dataset_format,
            )
            L.debug(
                "target<>working_copy diff (%s): %s",
                ds_path,
                repr(target_wc_diff),
            )

    ds_diff = DatasetDiff.concatenated(
        base_target_diff, target_wc_diff, overwrite_original=True
    )
    ds_diff.prune()
    return ds_diff
