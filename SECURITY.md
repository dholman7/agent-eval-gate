# Security

Report a vulnerability privately to danxholman@gmail.com, not in a public issue. Only `main` is supported.

`aeg run --command` executes the agent with your user's permissions. Each agent gets its own copy of the target repo, and scoring always uses a pristine copy, but that is isolation for correct results, not a sandbox. Run untrusted agents inside a container or a throwaway VM, and give them only the API keys they need.

In scope: a way for an agent's output to change its own score other than through the test files it writes (for example, by altering the pristine copy, the seeded bugs, or the results file).
