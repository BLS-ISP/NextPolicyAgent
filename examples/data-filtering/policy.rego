# Data Filtering & Projection Policy
# ====================================
# Shows how to filter, project, and aggregate data using Rego comprehensions.
# Useful for data APIs that need to return filtered subsets based on user permissions.
#
# Test: npa eval -d examples/data-filtering/ -i examples/data-filtering/input.json "data.filtering"

package filtering

# ── Filtered views ───────────────────────────────────────

# All active employees
active_employees := [emp |
    some emp in data.employees
    emp.active == true
]

# Active employees in the requested department
department_employees := [emp |
    some emp in data.employees
    emp.department == input.department
    emp.active == true
]

# Names of employees with top-secret clearance
top_secret_names := [emp.name |
    some emp in data.employees
    emp.clearance == "top-secret"
    emp.active == true
]

# Names of employees with at least secret clearance
cleared_names := [emp.name |
    some emp in data.employees
    emp.clearance == "top-secret"
]

cleared_names_secret := [emp.name |
    some emp in data.employees
    emp.clearance == "secret"
]

# ── Projections (select specific fields) ─────────────────

# Directory: just names and departments
directory := [{"name": emp.name, "department": emp.department} |
    some emp in data.employees
    emp.active == true
]

# ── Aggregations ─────────────────────────────────────────

total_employees := count(data.employees)

total_active := count([emp |
    some emp in data.employees
    emp.active == true
])

total_in_department := count([emp |
    some emp in data.employees
    emp.department == input.department
    emp.active == true
])

# ── Access control ───────────────────────────────────────
# Only managers and admins can see clearance information

default can_view_clearance = false

can_view_clearance if {
    input.viewer_role == "admin"
}

can_view_clearance if {
    input.viewer_role == "manager"
}

# ── Summary ──────────────────────────────────────────────
# Note: count() expressions are inlined since rule refs can't be used as sprintf args
summary := sprintf("Abteilung '%s': %s aktive Mitarbeiter gefunden", [input.department, count([emp | some emp in data.employees; emp.department == input.department; emp.active == true])])
