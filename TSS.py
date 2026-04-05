File "/mount/src/tss/TSS.py", line 142, in <module>
    today = datetime.now().strftime('%Y-%m-%d')
                                   ^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/core/frame.py", line 4378, in __getitem__
    indexer = self.columns.get_loc(key)
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/core/indexes/base.py", line 3648, in get_loc
    raise KeyError(key) from err