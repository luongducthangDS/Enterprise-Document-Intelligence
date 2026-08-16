-- Preserve a distinct audit timestamp when the requester/admin closes a resolved ticket.
alter table public.tickets
  add column if not exists closed_at timestamptz;
