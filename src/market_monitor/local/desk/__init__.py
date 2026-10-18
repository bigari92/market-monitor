"""The desk page: arithmetic over money already committed.

Lives in the repository (so it is versioned and reviewable) while the data and the
rendered reports stay in the personal folder, which has no remote. The split is the
point: this package reads C:/Users/valer/Investing read-only and copies nothing out of
it, so the code can be committed while the records cannot leak.

`paths.personal_root()` is the single place that knows where the personal folder is.
"""
