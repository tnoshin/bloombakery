document.querySelector(`form`).addEventListener(`submit`, function(event) {
    if (document.querySelector(`#Name`).value === ``) {
        event.preventDefault();
        alert(`Please fill in your name.`);
    } else if (document.querySelector(`#Email`).value === ``) {
        event.preventDefault();
        alert(`Please fill in your email.`);
    } else if (document.querySelector(`#Message`).value === ``) {
        event.preventDefault();
        alert(`Please write the message.`);
    }
})