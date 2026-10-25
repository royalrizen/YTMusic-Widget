# YTMusic Widget <img src="https://cdn.simpleicons.org/youtubemusic/FF0000" width="26" height="26" alt="YouTube Music">
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![YouTube Music](https://img.shields.io/badge/YouTube%20Music-FF0000?style=flat&logo=youtubemusic&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat&logo=githubactions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=flat&logo=githubpages&logoColor=white)


Ever wanted to show what you're listening to on YouTube Music on your GitHub profile? Finding a way to do that without an official API can be a pain.

YTMusic Widget solves that with a simple, dynamic SVG card that displays your latest listen right in your README.

## Demo

<img src="https://royalrizen.github.io/YTMusic-Widget/listening.svg" alt="My YouTube Music" width="440">

## How it works?

- Uses your YouTube Music session cookies to authenticate and fetch your listening history.
- Extracts the latest song's title, artist, and thumbnail.
- Generates an SVG card and a JSON file containing the track details.
- Uses GitHub Actions to run the script automatically at regular intervals. (5 minutes) :p
- Publishes the generated files to GitHub Pages so the card can be embedded in your README.

## Cool! How to use?

**1. Get your YouTube Music cookies**

- Log in to your YouTube Music account in Chrome.
- Press <kbd>F12</kbd> to open DevTools.
- Go to the Network tab and refresh the page.
- Look for the "/history" request and select it.
- Under Request Headers, copy the cookie data. Alternatively, you can copy the request as cURL, separate the cookie values and save them.

Save the cookies locally in a ".json" file using this format:
```json
{
  "cookiename": "cookievalue",
  "another_cookie": "another_value"
}
```

**2. Set up the repository**

- Fork this repository to your GitHub account.
- Go to Settings → Secrets and variables → Actions.
- Create a repository secret named "YTMUSIC_COOKIES".
- Paste the contents of your cookies JSON file as the secret value.

> [!CAUTION]
> Your cookies can grant access to your account. Never share them, commit them to your repository, or upload them anywhere else.

**3. Enable GitHub Pages**

- Go to Settings → Pages.
- Set the deployment source to GitHub Actions.

**4. Run the workflow**

- Open the Actions tab in your repository.
- Select the Update YouTube Music Card workflow.
- Click Run workflow and wait for it to finish.

Once the workflow completes successfully, your card should be available on GitHub Pages. You can then embed the SVG in your GitHub README.

## License
This project is licensed under the [MIT License](LICENSE).

## Support
If you find this project useful, consider giving it a ⭐ on GitHub. ♡
