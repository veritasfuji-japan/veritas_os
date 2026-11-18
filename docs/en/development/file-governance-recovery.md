# File governance recovery

File-backed governed updates and rollbacks write a sidecar journal at
<policy filename>.pending.json before replacing the current policy. The
journal stores the previous disk state, intended policy, history location,
and audit event with a unique event_id. Existing JSON policy files and
history records remain readable.

Policy reads, history reads, and repository writes check the journal under
the repository write lock. When the disk policy matches the intended policy,
recovery appends the missing audit event and removes the journal after syncing
the history. When the event ID already exists with identical contents, recovery
syncs the existing history and removes the journal without appending again.
History retention can replace the history file after an append. The repository
syncs the history directory again after retention before removing the journal,
including when policy and history are stored in different directories. An I/O
failure at this boundary preserves the journal and blocks reads until recovery
can sync the retained history.

When the disk policy still matches its previous state, recovery discards the
prepared operation. It does not apply the intended policy. A divergent policy,
unreadable journal, conflicting event ID, or continuing I/O failure prevents
the repository operation and preserves the journal for inspection.

A failed request can have changed the policy. Clients must inspect current
state before resubmitting. Pending recovery bypasses automatic Bind rollback
because another write could overwrite the state needed to reconcile the event.
A failed API response can contain a null policy when recovery remains blocked.
A Bind receipt from the interrupted or failed request is separate from the
recovered policy history event.

Recovery runs when the repository is next accessed. Administrators should
restore storage access and retain the journal until recovery succeeds.
The journal contains policy snapshots and uses owner-only temporary files.
It must be included with the policy and history in backups and kept in the
same trusted storage boundary.

The guarantee covers cooperating writers using the same policy/history paths.
Cross-process locking requires flock. Power-loss durability depends on the
filesystem honoring file and directory sync. Directory sync can be unavailable
and newly created ancestor directories have separate durability requirements.
The tests inject interruptions at persistence boundaries and reopen repository
instances. They do not simulate power removal or establish storage guarantees
for every filesystem.
