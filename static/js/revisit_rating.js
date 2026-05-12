document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-revisit-toggle]").forEach((visitedSelect) => {
        const form = visitedSelect.closest("form");
        const ratingGroup = form?.querySelector("[data-revisit-rating-group]");
        const zeroRating = form?.querySelector('input[name="revisit_rating"][value="0"]');

        if (!ratingGroup || !zeroRating) {
            return;
        }

        const syncRevisitRating = () => {
            const hasVisited = visitedSelect.value === "1";

            ratingGroup.classList.toggle("is-hidden", !hasVisited);

            if (!hasVisited) {
                zeroRating.checked = true;
            }
        };

        visitedSelect.addEventListener("change", syncRevisitRating);
        syncRevisitRating();
    });
});
