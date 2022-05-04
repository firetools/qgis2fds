from qgis.core import NULL

# FIXME Move to Terrain
def get_obsts(context, feedback, utm_origin, sampling_layer, surf_id_dict, pixel_size):
    """Get formatted OBSTs from sampling layer."""

    # Init
    nfeatures = sampling_layer.featureCount()
    partial_progress = nfeatures // 100 or 1

    left_idx = sampling_layer.fields().indexOf("left")
    right_idx = sampling_layer.fields().indexOf("right")
    top_idx = sampling_layer.fields().indexOf("top")
    bottom_idx = sampling_layer.fields().indexOf("bottom")
    landuse_idx = sampling_layer.fields().indexOf("landuse1")
    bc_idx = sampling_layer.fields().indexOf("bc")
    origin_x, origin_y = utm_origin.x(), utm_origin.y()
    overlap = 0.01

    # Read values
    xbs, lus, bcs = list(), list(), list()
    for i, f in enumerate(sampling_layer.getFeatures()):
        if i % partial_progress == 0:
            feedback.setProgress(int(i / nfeatures * 100))
        g, a = f.geometry().get(), f.attributes()
        xbs.append(
            tuple(
                (
                    a[left_idx] - origin_x - overlap,
                    a[right_idx] - origin_x + overlap,
                    a[bottom_idx] - origin_y - overlap,
                    a[top_idx] - origin_y + overlap,
                    0.0,
                    g.z(),
                )
            )
        )
        lus.append(a[landuse_idx])
        bcs.append(a[bc_idx])

    # Calc min and max z (also for MESH)
    min_z = min(xb[5] for xb in xbs) - pixel_size
    max_z = max(xb[5] for xb in xbs)

    # Prepare OBSTs
    obsts = list()
    for i in range(len(xbs)):
        xb = xbs[i]
        if bcs[i] == NULL:
            surf_id = surf_id_dict[lus[i]]
        else:
            surf_id = surf_id_dict[bcs[i]]
        obsts.append(
            f"&OBST XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},{min_z:.2f},{xb[5]:.2f} SURF_ID='{surf_id}' /"
        )

    return obsts, min_z, max_z
