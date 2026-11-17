const liveAuction = document.getElementById("live-auction");
const bidFields = document.getElementById("bid-fields");
let clockLoadedAt = performance.now();

function updateCountdown() {
    const clock = document.getElementById("auction-clock");
    const countdown = document.getElementById("countdown");
    const status = clock.dataset.status;
    bidFields.disabled = status !== "Active";
    if (!countdown) {
        return;
    }

    const elapsed = (performance.now() - clockLoadedAt) / 1000;
    const seconds = Math.max(0, Math.ceil(Number(clock.dataset.target) - Number(clock.dataset.now) - elapsed));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor(seconds / 60) % 60;
    countdown.textContent = [hours, minutes, seconds % 60]
        .map((part) => String(part).padStart(2, "0"))
        .join(":");

    if (seconds === 0) {
        bidFields.disabled = true;
    }
}

async function refreshAuction() {
    try {
        const response = await fetch(liveAuction.dataset.url);
        if (response.ok) {
            liveAuction.innerHTML = await response.text();
            clockLoadedAt = performance.now();
            updateCountdown();
        }
    } catch {
        // Keep the last snapshot visible until the next refresh.
    } finally {
        const status = document.getElementById("auction-clock").dataset.status;
        if (status === "Active" || status === "Scheduled") {
            setTimeout(refreshAuction, 3000);
        }
    }
}

updateCountdown();
setInterval(updateCountdown, 500);
setTimeout(refreshAuction, 3000);
