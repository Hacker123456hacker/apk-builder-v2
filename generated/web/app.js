document.addEventListener('DOMContentLoaded', () => {
    const actionButton = document.getElementById('actionButton');
    const messageElement = document.getElementById('message');

    let clickCount = 0;

    actionButton.addEventListener('click', () => {
        clickCount++;
        if (clickCount === 1) {
            messageElement.textContent = 'You clicked the button!';
        } else {
            messageElement.textContent = `You clicked ${clickCount} times!`;
        }
        console.log(`Button clicked ${clickCount} times.`);
    });
});
