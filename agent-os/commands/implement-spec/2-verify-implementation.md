Now that the implementation of this spec is complete, we must generate an ordered series of verification prompt texts, which will be used to verify the implementation of this spec's tasks.

Follow these steps to generate this spec's ordered series of verification prompt texts, each in its own .md file located in `agent-os/specs/[this-spec]/implementation/prompts/`.

## Verification Prompt Generation Workflow

### Step 1: Determine which verifier roles are needed

1. Read `agent-os/specs/[this-spec]/tasks.md` to identify all implementer roles that were assigned to task groups.

2. Read `agent-os/roles/implementers.yml` and for each implementer role that was used:
   - Find that implementer by ID
   - Note the verifier role(s) listed in its `verified_by` field

3. Collect all unique verifier roles from this process (e.g., backend-verifier, frontend-verifier).

4. Read `agent-os/roles/verifiers.yml` to confirm these verifier roles exist and understand their responsibilities.

### Step 2: Generate verification prompt files for each verifier

For EACH unique verifier role identified in Step 1, create a verification prompt file.

#### Step 2a. Create the verifier prompt markdown file

Create the prompt markdown file using this naming convention:
`agent-os/specs/[this-spec]/implementation/prompts/[next-number]-verify-[verifier-name].md`

For example, if the last implementation prompt was `4-comment-system.md` and you need to verify backend and frontend:
- Create `5-verify-backend.md`
- Create `6-verify-frontend.md`

#### Step 2b. Populate the verifier prompt file

Populate the verifier prompt markdown file using the following Prompt file content template.

##### Bracket content replacements

In the content template below, replace "[spec-title]" and "[this-spec]" with the current spec's title.

Replace "[verifier-role-name]" with the verifier role's ID (e.g., "backend-verifier").

Replace "[task-groups-list]" with a bulleted list of the task group titles (parent tasks only) that fall under this verifier's purview. To determine which task groups:
1. Look at all task groups in `tasks.md`
2. For each task group, check its assigned implementer
3. If that implementer's `verified_by` field includes this verifier role, include this task group in the list

Replace "[verifier-standards]" using the following logic:
1. Find the verifier role in `agent-os/roles/verifiers.yml`
2. Check the list of `standards` for that verifier
3. Compile the list of file references to those standards and display the list in place of "[verifier-standards]", one file reference per line. Use this logic for determining the list of files to include:
   a. If the value for `standards` is simply `all`, then include every single file, folder, sub-folder and files within sub-folders in your list of files.
   b. If the item under standards ends with "*" then it means that all files within this folder or sub-folder should be included. For example, `frontend/*` means include all files and sub-folders and their files located inside of `agent-os/standards/frontend/`.
   c. If a file ends in `.md` then it means this is one specific file you must include in your list of files. For example `backend/api.md` means you must include the file located at `agent-os/standards/backend/api.md`.
   d. De-duplicate files in your list of file references.

The compiled list of standards should look like this, where each file reference is on its own line and begins with `@`. The exact list of files will vary:

```
@agent-os/standards/global/coding-style.md
@agent-os/standards/global/conventions.md
@agent-os/standards/global/tech-stack.md
@agent-os/standards/backend/api.md
@agent-os/standards/backend/migrations.md
@agent-os/standards/testing/test-writing.md
```

##### Verifier prompt file content template:

```markdown
We're verifying the implementation of [spec-title] by running verification for tasks under the [verifier-role-name] role's purview.

## Task groups under your verification purview

The following task groups have been implemented and need your verification:

[task-groups-list]

## Understand the context

Read @agent-os/specs/[this-spec]/spec.md to understand the context for this spec and where these tasks fit into it.

## Your verification responsibilities

1. **Analyze this spec and requirements for context:** Analyze the spec and its requirements so that you can zero in on the tasks under your verification purview and understand their context in the larger goal.
2. **Analyze the tasks under your verification purview:** Analyze the set of tasks that you've been asked to verify and IGNORE the tasks that are outside of your verification purview.
3. **Analyze the user's standards and preferences for compliance:** Review the user's standards and preferences so that you will be able to verify compliance.
4. **Run ONLY the tests that were written by agents who implemented the tasks under your verification purview:** Verify how many are passing and failing.
5. **(if applicable) view the implementation in a browser:** If your verification purview involves UI implementations, open a browser to view, verify and take screenshots and store screenshot(s) in `agent-os/specs/[this-spec]/verification/screenshots`.
6. **Verify tasks.md status has been updated:** Verify and ensure that the tasks in `tasks.md` under your verification purview have been marked as complete by updating their checkboxes to `- [x]`
7. **Verify that implementations have been documented:** Verify that the implementer agent(s) have documented their work in this spec's `agent-os/specs/[this-spec]/implementation`. folder.
8. **Document your verification report:** Write your verification report in this spec's `agent-os/specs/[this-spec]/verification`. folder.


## User Standards & Preferences Compliance

IMPORTANT: Ensure that your verification work validates ALIGNMENT and IDENTIFIES CONFLICTS with the user's preferences and standards as detailed in the following files:

[verifier-standards]

```

### Step 3: Generate the final verification prompt

After all verifier-specific prompts have been created, create ONE final verification prompt that will perform the end-to-end verification.

#### Step 3a. Create the final verification prompt markdown file

Create the prompt markdown file using this naming convention:
`agent-os/specs/[this-spec]/implementation/prompts/[next-number]-verify-implementation.md`

For example, if the last verifier prompt was `6-verify-frontend.md`, create `7-verify-implementation.md`.

#### Step 3b. Populate the final verification prompt file

Use the following content template for the final verification prompt:

```markdown
We're completing the verification process for [spec-title] by performing the final end-to-end verification and producing the final verification report.

## Understand the context

Read @agent-os/specs/[this-spec]/spec.md to understand the full context of this spec.

## Your role

You are performing the final implementation verification using the **implementation-verifier** role.

## Perform final verification

Follow the implementation-verifier workflow to complete your verification:

### Step 1: Ensure tasks.md has been updated

Check `agent-os/specs/[this-spec]/tasks.md` and ensure that all tasks and their sub-tasks are marked as completed with `- [x]`.

If a task is still marked incomplete, then verify that it has in fact been completed by checking the following:
- Run a brief spot check in the code to find evidence that this task's details have been implemented
- Check for existence of an implementation report titled using this task's title in `agent-os/spec/[this-spec]/implementation/` folder.

IF you have concluded that this task has been completed, then mark it's checkbox and its' sub-tasks checkboxes as completed with `- [x]`.

IF you have concluded that this task has NOT been completed, then mark this checkbox with ⚠️ and note it's incompleteness in your verification report.


### Step 2: Verify that implementations and verifications have been documented

Check `agent-os/specs/[this-spec]/implementations` folder to confirm that each task group from this spec's `tasks.md` has an associated implementation document that is named using the number and title of the task group.

For example, if the 3rd task group is titled "Commenting System", then the implementer of that task group should have already created an implementation document named `agent-os/specs/[this-spec]/implementations/3-commenting-system-implementation.md`.

If documentation is missing for any task group, include this in your final verification report.


### Step 3: Update roadmap (if applicable)

Open `agent-os/product/roadmap.md` and check to see whether any item(s) match the description of the current spec that has just been implemented.  If so, then ensure that these item(s) are marked as completed by updating their checkbox(s) to `- [x]`.


### Step 4: Run entire tests suite

Run the entire tests suite for the application so that ALL tests run.  Verify how many tests are passing and how many have failed or produced errors.

Include these counts and the list of failed tests in your final verification report.

DO NOT attempt to fix any failing tests.  Just note their failures in your final verification report.


### Step 5: Create final verification report

Create your final verification report in `agent-os/specs/[this-spec]/verifications/final-verification.html`.

The content of this report should follow this structure:

```markdown
# Verification Report: [Spec Title]

**Spec:** `[spec-name]`
**Date:** [Current Date]
**Verifier:** implementation-verifier
**Status:** ✅ Passed | ⚠️ Passed with Issues | ❌ Failed

---

## Executive Summary

[Brief 2-3 sentence overview of the verification results and overall implementation quality]

---

## 1. Tasks Verification

**Status:** ✅ All Complete | ⚠️ Issues Found

### Completed Tasks
- [x] Task Group 1: [Title]
  - [x] Subtask 1.1
  - [x] Subtask 1.2
- [x] Task Group 2: [Title]
  - [x] Subtask 2.1

### Incomplete or Issues
[List any tasks that were found incomplete or have issues, or note "None" if all complete]

---

## 2. Documentation Verification

**Status:** ✅ Complete | ⚠️ Issues Found

### Implementation Documentation
- [x] Task Group 1 Implementation: `implementations/1-[task-name]-implementation.md`
- [x] Task Group 2 Implementation: `implementations/2-[task-name]-implementation.md`

### Verification Documentation
[List verification documents from area verifiers if applicable]

### Missing Documentation
[List any missing documentation, or note "None"]

---

## 3. Roadmap Updates

**Status:** ✅ Updated | ⚠️ No Updates Needed | ❌ Issues Found

### Updated Roadmap Items
- [x] [Roadmap item that was marked complete]

### Notes
[Any relevant notes about roadmap updates, or note if no updates were needed]

---

## 4. Test Suite Results

**Status:** ✅ All Passing | ⚠️ Some Failures | ❌ Critical Failures

### Test Summary
- **Total Tests:** [count]
- **Passing:** [count]
- **Failing:** [count]
- **Errors:** [count]

### Failed Tests
[List any failing tests with their descriptions, or note "None - all tests passing"]

### Notes
[Any additional context about test results, known issues, or regressions]
```


```

### Step 4: Output the list of created verification prompt files

Output to user the following:

"Ready to begin verification of [spec-title]!

Use the following list of verification prompts to direct the verification process:

[list all verification prompt files in order]

Input those prompts into this chat one-by-one or queue them to run in order.

Verification results will be documented in `agent-os/specs/[this-spec]/verification/`"
