const TEAMS = [
    { name: "United States", code: "us" },
    { name: "Mexico", code: "mx" },
    { name: "Canada", code: "ca" },
    { name: "Spain", code: "es" },
    { name: "Argentina", code: "ar" },
    { name: "France", code: "fr" },
    { name: "England", code: "gb-eng" },
    { name: "Brazil", code: "br" },
    { name: "Portugal", code: "pt" },
    { name: "Netherlands", code: "nl" },
    { name: "Belgium", code: "be" },
    { name: "Germany", code: "de" },
    { name: "Croatia", code: "hr" },
    { name: "Morocco", code: "ma" },
    { name: "Colombia", code: "co" },
    { name: "Uruguay", code: "uy" },
    { name: "Switzerland", code: "ch" },
    { name: "Japan", code: "jp" },
    { name: "Senegal", code: "sn" },
    { name: "Iran", code: "ir" },
    { name: "South Korea", code: "kr" },
    { name: "Ecuador", code: "ec" },
    { name: "Austria", code: "at" },
    { name: "Australia", code: "au" },
    { name: "Norway", code: "no" },
    { name: "Panama", code: "pa" },
    { name: "Egypt", code: "eg" },
    { name: "Algeria", code: "dz" },
    { name: "Scotland", code: "gb-sct" },
    { name: "Paraguay", code: "py" },
    { name: "Tunisia", code: "tn" },
    { name: "Ivory Coast", code: "ci" },
    { name: "Uzbekistan", code: "uz" },
    { name: "Qatar", code: "qa" },
    { name: "Saudi Arabia", code: "sa" },
    { name: "South Africa", code: "za" },
    { name: "Jordan", code: "jo" },
    { name: "Cape Verde", code: "cv" },
    { name: "Ghana", code: "gh" },
    { name: "Cura\u00e7ao", code: "cw" },
    { name: "Haiti", code: "ht" },
    { name: "New Zealand", code: "nz" },
    { name: "Bosnia and Herzegovina", code: "ba" },
    { name: "Sweden", code: "se" },
    { name: "Turkey", code: "tr" },
    { name: "Czech Republic", code: "cz" },
    { name: "Iraq", code: "iq" },
    { name: "DR Congo", code: "cd" }
];

const flagBig = code => `https://flagcdn.com/w320/${code}.png`;
const flagSmall = code => `https://flagcdn.com/w40/${code}.png`;

let order = [];
let current = 0;
let answers = [];
let revealed = false;

const $ = id => document.getElementById(id);

function shuffle(items) {
    const shuffled = items.slice();
    for (let index = shuffled.length - 1; index > 0; index--) {
        const swapIndex = Math.floor(Math.random() * (index + 1));
        [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
    }
    return shuffled;
}

function startQuiz() {
    order = shuffle(TEAMS);
    current = 0;
    answers = [];
    $("quiz-total").textContent = `${TEAMS.length} teams`;
    $("report").classList.add("hidden");
    $("quiz").classList.remove("hidden");
    renderFlag();
}

function renderFlag() {
    const team = order[current];
    revealed = false;
    $("flagImg").src = flagBig(team.code);
    $("flagImg").alt = `National flag ${current + 1}`;
    $("counter").textContent = `Flag ${current + 1} of ${order.length}`;
    $("progressBar").style.width = `${(current / order.length) * 100}%`;

    const reveal = $("reveal");
    reveal.classList.remove("show");
    reveal.innerHTML = "&nbsp;";

    $("guessButtons").classList.remove("hidden");
    $("answerButtons").classList.add("hidden");
    $("btnGuess").focus();
}

function revealCountry() {
    if (revealed) return;
    revealed = true;
    const reveal = $("reveal");
    reveal.textContent = order[current].name;
    reveal.classList.add("show");
    $("guessButtons").classList.add("hidden");
    $("answerButtons").classList.remove("hidden");
    $("btnYes").focus();
}

function advance() {
    current++;
    if (current < order.length) {
        renderFlag();
    } else {
        showReport();
    }
}

function answer(known) {
    if (!revealed) return;
    answers.push({ team: order[current], known });
    advance();
}

function showReport() {
    $("quiz").classList.add("hidden");
    $("report").classList.remove("hidden");
    $("progressBar").style.width = "100%";

    const known = answers.filter(answerItem => answerItem.known);
    const missed = answers.filter(answerItem => !answerItem.known);
    const total = answers.length;
    const pct = total === 0 ? 0 : Math.round((known.length / total) * 100);

    $("scoreVal").textContent = `${pct}%`;
    $("scoreMsg").textContent = scoreMessage(pct);
    $("yesCount").textContent = known.length;
    $("noCount").textContent = missed.length;
    $("totalCount").textContent = total;

    fillAllResultsList($("allFlagsList"), answers);
    $("btnRetry").focus();
}

function scoreMessage(pct) {
    if (pct === 100) return "Perfect round.";
    if (pct >= 80) return "Excellent flag knowledge.";
    if (pct >= 60) return "Strong result with a few to brush up on.";
    if (pct >= 40) return "Good start.";
    return "Plenty to learn next round.";
}

function fillAllResultsList(list, items) {
    list.innerHTML = "";
    if (items.length === 0) {
        const item = document.createElement("li");
        const note = document.createElement("span");
        note.className = "empty-note";
        note.textContent = "No flags answered yet.";
        item.appendChild(note);
        list.appendChild(item);
        return;
    }

    items.forEach(({ team, known }) => {
        const item = document.createElement("li");
        const image = document.createElement("img");
        const label = document.createElement("span");
        const status = document.createElement("span");

        image.src = flagSmall(team.code);
        image.alt = team.name;
        label.textContent = team.name;
        label.className = "flag-name";
        status.className = known ? "flag-status recognized" : "flag-status missed";
        status.textContent = known ? "Recognized" : "Missed";

        item.appendChild(image);
        item.appendChild(label);
        item.appendChild(status);
        list.appendChild(item);
    });
}

function handleKeydown(event) {
    if ($("quiz").classList.contains("hidden")) return;

    if (event.key === " " || event.code === "Space") {
        event.preventDefault();
        revealCountry();
    } else if (event.key === "y" || event.key === "Y") {
        answer(true);
    } else if (event.key === "n" || event.key === "N") {
        answer(false);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (window.createParticles) {
        window.createParticles($("quiz-particles"), 24);
    }

    $("btnGuess").addEventListener("click", revealCountry);
    $("btnYes").addEventListener("click", () => answer(true));
    $("btnNo").addEventListener("click", () => answer(false));
    $("btnRetry").addEventListener("click", startQuiz);
    document.addEventListener("keydown", handleKeydown);

    startQuiz();
});