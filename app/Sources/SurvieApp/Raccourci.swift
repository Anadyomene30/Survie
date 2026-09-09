import AppKit
import Carbon.HIToolbox

/// Raccourci global ⌥⌘S.
///
/// Enregistré au niveau du système : il ouvre le panneau même quand une autre
/// application est au premier plan. C'est le seul intérêt d'une application en
/// barre de menus pour cet usage — pouvoir poser une question sans quitter ce
/// qu'on fait.
///
/// Note : un raccourci global exige que l'application soit autorisée dans
/// Réglages Système → Confidentialité et sécurité → Accessibilité, sauf si
/// l'on passe par l'API Carbon `RegisterEventHotKey`, qui n'a pas cette
/// contrainte. C'est la voie retenue ici.
final class Raccourci {
    private var reference: EventHotKeyRef?
    private var gestionnaire: EventHandlerRef?
    private let action: () -> Void

    private static var actif: Raccourci?

    init(action: @escaping () -> Void) {
        self.action = action
    }

    func installer() {
        Self.actif = self

        var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ -> OSStatus in
            Raccourci.actif?.action()
            return noErr
        }, 1, &type, nil, &gestionnaire)

        var identifiant = EventHotKeyID(signature: OSType(0x53525649), id: 1)  // "SRVI"
        RegisterEventHotKey(UInt32(kVK_ANSI_S),
                            UInt32(optionKey | cmdKey),
                            identifiant, GetApplicationEventTarget(), 0, &reference)
    }

    deinit {
        if let reference { UnregisterEventHotKey(reference) }
        if let gestionnaire { RemoveEventHandler(gestionnaire) }
    }
}
