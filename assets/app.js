const REPO_OWNER = "Hacker123456hacker";
const REPO_NAME = "apk-builder-v2";
const formButton = document.getElementById("submitIdea");
const ideaField = document.getElementById("idea");
formButton.addEventListener("click", () => {
  const idea = ideaField.value.trim();
  if (idea.length < 20) {
    ideaField.focus();
    alert("Please describe your idea in at least 20 characters.");
    return;
  }
  const title = encodeURIComponent("Build idea: " + idea.slice(0, 70).replace(/\s+/g, " "));
  const body = encodeURIComponent("## My idea\n\n" + idea + "\n\n## Requested output\n- [x] Android APK\n- [x] Website option\n\n## Workflow\nCreate a draft for review first. Do not build or publish until I approve it.");
  const url = "https://github.com/" + REPO_OWNER + "/" + REPO_NAME + "/issues/new?title=" + title + "&body=" + body + "";
  window.location.href = url;
});