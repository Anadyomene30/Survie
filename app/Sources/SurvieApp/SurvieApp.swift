import SurvieCore
import SwiftUI

@main
struct SurvieApp: App {
    @StateObject private var reglages: Reglages
    @StateObject private var modele: ModeleVue
    @State private var raccourci: Raccourci?
    @Environment(\.openWindow) private var ouvrirFenetre

    init() {
        let r = Reglages()
        _reglages = StateObject(wrappedValue: r)
        _modele = StateObject(wrappedValue: ModeleVue(reglages: r))
    }

    var body: some Scene {
        MenuBarExtra {
            PanneauView(modele: modele, reglages: reglages)
                .frame(width: 640, height: 720)
                .task {
                    guard raccourci == nil else { return }
                    // ⌥⌘S bascule le mode urgence sans quitter ce qu'on fait.
                    // MenuBarExtra n'expose pas d'API pour s'ouvrir par
                    // programme ; le raccourci agit donc sur l'état, et le
                    // panneau le reflète à sa prochaine ouverture. À revoir si
                    // une API d'ouverture apparaît.
                    let r = Raccourci { modele.modeUrgence.toggle() }
                    r.installer()
                    raccourci = r
                }
        } label: {
            // Une icône qui change en mode urgence : on doit voir d'un coup
            // d'œil dans quel mode on est.
            Image(systemName: modele.modeUrgence ? "cross.case.fill" : "leaf.fill")
        }
        .menuBarExtraStyle(.window)

        Settings {
            VueReglages(reglages: reglages)
        }
    }
}
