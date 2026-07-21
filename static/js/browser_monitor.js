console.log("browser_monitor.js loaded");

let focusLossCount = 0;
let lastFocusLossTime = "-";
let browserActive = true;

// Update browser status
function updateBrowserStatus(status) {

    console.log("Status Updated:", status);

    document.getElementById("browserStatus").innerText = status;
}

// Send event to Flask
function logBrowserEvent(eventType, remarks) {

    console.log("Sending Event:", eventType);

    fetch("/browser_event", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            event_type: eventType,
            remarks: remarks
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log("Server Response:", data);
    })
    .catch(error => {
        console.error("Fetch Error:", error);
    });

}

// Handle browser losing focus
function handleFocusLost(reason) {

    if (!browserActive) return;

    console.log("Browser Lost Focus");

    browserActive = false;

    updateBrowserStatus("Browser Inactive");

    focusLossCount++;

    lastFocusLossTime = new Date().toLocaleString();

    document.getElementById("focusCount").innerText = focusLossCount;
    document.getElementById("lastLossTime").innerText = lastFocusLossTime;

    logBrowserEvent(
        "Browser Focus Lost",
        reason
    );
}

// Handle browser regaining focus
function handleFocusRegained(reason) {

    if (browserActive) return;

    console.log("Browser Regained Focus");

    browserActive = true;

    updateBrowserStatus("Browser Active");

    logBrowserEvent(
        "Browser Focus Regained",
        reason
    );
}

// Alt + Tab / Another Application
window.addEventListener("blur", function () {

    console.log("Blur Event Fired");

    handleFocusLost(
        "Candidate switched away from the examination window."
    );

});

// Browser Active Again
window.addEventListener("focus", function () {

    console.log("Focus Event Fired");

    handleFocusRegained(
        "Candidate returned to the examination window."
    );

});

// Browser Tab Switching
document.addEventListener("visibilitychange", function () {

    console.log("Visibility Changed:", document.hidden);

    if (document.hidden) {

        handleFocusLost(
            "Candidate switched to another browser tab."
        );

    } else {

        handleFocusRegained(
            "Candidate returned to the examination tab."
        );

    }

});