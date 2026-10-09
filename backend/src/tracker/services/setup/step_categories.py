"""Step 4b: your categories, chosen from a preset and your own.

It can be skipped; the skip is remembered, so a later full run does not ask again.
"""

from __future__ import annotations

from tracker.services.profile.choice import SavedChoice
from tracker.services.profile.chooser import CategoryChooser
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.skipped_steps import remember_skip, skipped_earlier


class CategoriesStep:
    """Asks which categories to sort people into, and saves them to the database."""

    name = StepName.CATEGORIES
    title = "Your categories"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done once a preset is saved: only a confirmed choice saves one."""
        return ctx.choices().chosen_preset() is not None

    async def run(self, ctx: SetupContext) -> None:
        """Explain categories, then ask for them, or keep the defaults when skipped."""
        if skipped_earlier(ctx, self.name, "To choose them"):
            return
        io = ctx.io
        io.say("Threadline puts each person you talk to in a category, such as")
        io.say("'Startup' or 'Investor'. You pick a list that fits what you track,")
        io.say("keep the categories you use, and add your own.")
        if not io.confirm("Choose your categories now?", default=True):
            remember_skip(ctx, self.name)
            _say_defaults_kept(ctx)
            return
        choice = CategoryChooser(io).choose()
        if choice is None:
            _say_defaults_kept(ctx)
            return
        _say_saved(ctx, ctx.choices().save(choice))


def _say_defaults_kept(ctx: SetupContext) -> None:
    """Tell the owner nothing changed, and where to choose later."""
    ctx.io.say("Nothing saved: your categories stay as they are (the job-search ones")
    ctx.io.say("if you have not chosen before). Change them any time on the dashboard's")
    ctx.io.say(f"Settings page, or run 'uv run tracker setup {StepName.CATEGORIES}'.")


def _say_saved(ctx: SetupContext, saved: SavedChoice) -> None:
    """Say, in plain words, what saving the choice did."""
    io = ctx.io
    io.say(f"Saved {len(saved.changes.saved)} categories, 'Not known' included.")
    if saved.changes.archived:
        io.say(f"Hidden, because people still have them: {', '.join(saved.changes.archived)}.")
    if saved.changes.renamed:
        names = ", ".join(f"'{category.label}'" for category in saved.changes.renamed)
        io.say(f"Renamed while hidden, so no two categories share a name: {names}.")
    if saved.profile_file_wins:
        io.say("Note: your own profile/profile.toml file exists, so its wording is still")
        io.say("used. Remove it to use the wording of the list you chose.")
    io.say("The AI helper will sort people into these from the next morning run.")
